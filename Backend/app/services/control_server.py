# -----------------------------------------------
# Import libraries to initialize TCP Server
# -----------------------------------------------
import app.services.http_client as http_client
import app.services.handle_data as handle_data


import asyncio
import numpy as np
import json
import ssl
import paho.mqtt.client as mqtt

from datetime import datetime
import time

# -----------------------------------------------
# Import 
# -----------------------------------------------
import app.environment.environment as environment
import importlib
import socket

import app.services.control_server as control_server
import app.environment.environment_manager as environment_manager
import app.routes.api.system_log as system_log
# -----------------------------------------------
# Global variables
# -----------------------------------------------
server = None  # Store server reference

# Global counter (uint32)
count = np.uint32(0)

# Maps client_ip -> client_id_hex
ip_to_id_map = {}

# Maps client_ip -> current writer (so we can close the old writer if the same IP reconnects)
ip_to_writer_map = {}

server = None  # Stores the running TCP server task
server_task = None  # Stores the running TCP server task


# -----------------------------------------------
# Function to start the TCP server
# -----------------------------------------------
async def start_tcp_server():
    global server_task
    if server_task is None:  # Prevent multiple instances
        print("[INFO] Starting TCP Server...")
        system_log.log_to_redis("[INFO] Starting TCP Server...")
        server_task = asyncio.create_task(run_tcp_server())
        
        # Update status of server
        environment_manager.update_status_tcp_server(True)

# -----------------------------------------------
# TCP Server Runner
# -----------------------------------------------
async def run_tcp_server():
    global server, server_task

    if server is not None:  # Prevent multiple instances
        print("[WARNING] TCP Server is already running.")
        system_log.log_to_redis("[WARNING] TCP Server is already running.")
        return
    try:
        server = await asyncio.start_server(
            control_server.handle_client,
            host=environment.TCP_SERVER_HOST,
            port=environment.TCP_SERVER_PORT
        )

        addrs = ', '.join(str(sock.getsockname()) for sock in server.sockets)

        print(f"[Async] TCP Server is running on {addrs}")
        system_log.log_to_redis(f"[Async] TCP Server is running on {addrs}")

        async with server:
            await server.serve_forever()

        print("[DEBUG] Waiting 2 seconds before starting server...")
        system_log.log_to_redis("[DEBUG] Waiting 2 seconds before starting server...")

        await asyncio.sleep(2)

    
    except OSError as e:
        print(f"[ERROR] Failed to start TCP Server: {e}")
        system_log.log_to_redis(f"[ERROR] Failed to start TCP Server: {e}")
        
# -----------------------------------------------
# Function to stop the TCP server
# -----------------------------------------------
async def stop_tcp_server():
    global server, server_task, ip_to_writer_map

    if server is not None:
        print("[INFO] Stopping TCP Server...")
        system_log.log_to_redis("[INFO] Stopping TCP Server...")

        # Close all active client connections
        for writer in list(ip_to_writer_map.values()):  # Close all active client sockets
            writer.close()
            try:
                await writer.wait_closed()  # Ensure closure
            except Exception as e:
                print(f"[WARNING] Error closing client socket: {e}")
                system_log.log_to_redis(f"[WARNING] Error closing client socket: {e}")
                writer.transport.abort()  # Force close if needed

        ip_to_writer_map.clear()  # Clear all connections

        # Stop the server
        server.close()
        try:
            await asyncio.wait_for(server.wait_closed(), timeout=5)
        except asyncio.TimeoutError:
            print("[WARNING] Server took too long to close, forcing shutdown.")
            system_log.log_to_redis("[WARNING] Server took too long to close, forcing shutdown.")

        server = None
        server_task = None
        environment_manager.update_status_tcp_server(False)

        system_log.log_to_redis("[INFO] TCP Server stopped.")
        print("[INFO] TCP Server stopped.")

# -----------------------------------------------
# Background task to refresh the AUTH_TOKEN
# every 3 hours (10800 seconds)
# -----------------------------------------------
async def refresh_auth_token():
    while True:
        await asyncio.sleep(10800)  # 3 hours in seconds
        try:
            auth_token = http_client.login_access_token(environment.USERNAME, environment.PASSWORD)
            environment_manager.update_auth_token(auth_token)
            print("[Auth Refresh] Successfully refreshed AUTH_TOKEN.")
        except Exception as e:
            print(f"[Auth Refresh] Exception while refreshing token: {e}")

# -----------------------------------------------
# Handle MQTT Publish
# -----------------------------------------------
def on_publish(client, userdata, mid):
    environment_manager.update_status_aws_server(True)

    print(f"[MQTT] Successfully published message ID={mid}")
    system_log.log_to_redis(f"[MQTT] Successfully published message ID={mid}")

# -----------------------------------------------
# Function to handle client connections
# -----------------------------------------------        
async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    global count

    mqtt_client = None

    client_address = writer.get_extra_info('peername')
    if not client_address:
        # Some cases where writer.get_extra_info('peername') could return None (if the socket closed quickly)
        print("[handle_client] Could not retrieve peername (client_address)")
        system_log.log_to_redis("[handle_client] Could not retrieve peername (client_address)")

        writer.close()
        await writer.wait_closed()
        return

    client_ip = client_address[0]

    print(f"[Async] Handling new client from IP={client_ip}")
    system_log.log_to_redis(f"[Async] Handling new client from IP={client_ip}")

    # If an existing writer for this IP exists, close it (enforcing "one IP - one connection")
    if client_ip in ip_to_writer_map:
        old_writer = ip_to_writer_map[client_ip]
        try:
            old_writer.close()
        except:
            pass
        await old_writer.wait_closed()

        print(f"[Async] Closed old connection for IP={client_ip}")
        system_log.log_to_redis(f"[Async] Closed old connection for IP={client_ip}")

    # Record the new writer for this IP
    ip_to_writer_map[client_ip] = writer

    # Increase 'count' if this is the first time we see this IP
    if client_ip not in ip_to_id_map:
        count += 1

    try:
        while True:
            # ----------------------------------------------------------
            #  Add exception handling for connection-reset errors
            # ----------------------------------------------------------
            try:
                data = await reader.read(1024)
            except (ConnectionResetError, BrokenPipeError) as e:
                print(f"[Async] Connection error from {client_ip}: {e}")
                system_log.log_to_redis(f"[Async] Connection error from {client_ip}: {e}")
                break

            if not data:
                # Client closed the connection
                print(f"[Async] Client {client_ip} disconnected.")
                system_log.log_to_redis(f"[Async] Client {client_ip} disconnected.")
                break

            print(f"Received data (hex): {data.hex()}")
            system_log.log_to_redis(f"Received data (hex): {data.hex()}")

            request_id, function, content_len, content_data = handle_data.parse_packet(data)

            print(f"[Parsed] function=0x{function:04x}, content_len={content_len}, content_data={content_data.hex()}")
            system_log.log_to_redis(f"[Parsed] function=0x{function:04x}, content_len={content_len}, content_data={content_data.hex()}")
            # ---------------- Handle function=0x0001 (register ID, send count) ----------------
            if function == 0x0001:
                # Suppose the last 13 bytes are the ID
                if len(content_data) >= 13:
                    new_id_hex = content_data[-13:].hex()
                else:
                    new_id_hex = "TooShort"

                http_client.register_device(new_id_hex)

                ip_to_id_map[client_ip] = new_id_hex

                print(f"[Server] (1) Registered new: IP={client_ip}, ID={new_id_hex}. count={count}")
                system_log.log_to_redis(f"[Server] (1) Registered new: IP={client_ip}, ID={new_id_hex}. count={count}")

                # ---------------- MQTT Setup ----------------
                mqtt_client = mqtt.Client(client_id=new_id_hex)

                mqtt_client.on_publish = on_publish

                # Configure SSL for secure connections to AWS IoT
                mqtt_client.tls_set(ca_certs=environment.root_ca_path,
                                    certfile=environment.cert_path,
                                    keyfile=environment.private_key_path,
                                    tls_version=ssl.PROTOCOL_TLSv1_2)

                system_log.log_to_redis(environment.AWS_IOT_ENDPOINT)
                system_log.log_to_redis(environment.MQTT_PORT)
                # Connect to broker
                mqtt_client.connect(environment.AWS_IOT_ENDPOINT, environment.MQTT_PORT, 60)

                # Start a background thread to handle the network loop
                mqtt_client.loop_start()

                # Build a response that contains 'count'
                data_resp = [
                    0x13, 0x01, 0x00, 0x02,
                    (request_id >> 24) & 0xFF,
                    (request_id >> 16) & 0xFF,
                    (request_id >> 8) & 0xFF,
                    (request_id >> 0) & 0xFF,
                    0, 0, 0, 0, 0, 6, 0, 1,
                    (count >> 24) & 0xFF,
                    (count >> 16) & 0xFF,
                    (count >> 8) & 0xFF,
                    (count >> 0) & 0xFF
                ]
                writer.write(bytes(data_resp))
                await writer.drain()
                print(f"[Server] Sent response for function=1 with count={count}")
                system_log.log_to_redis(f"[Server] Sent response for function=1 with count={count}")

            # ---------------- Handle function=0x03e8 (28 or 36 bytes of data) ----------------
            elif function == 0x03e8:

                client_id = ip_to_id_map.get(client_ip, "UnknownID")

                if client_id == "UnknownID":
                    data_req = [
                        0x13, 0x01, 0x01, 0x01,
                        (request_id >> 24) & 0xFF,
                        (request_id >> 16) & 0xFF,
                        (request_id >> 8) & 0xFF,
                        (request_id >> 0) & 0xFF,
                        0, 0, 0, 0, 0, 6, 0x04, 0x10,
                        0, 0, 0, 0
                    ]
                    writer.write(bytes(data_req))
                    await writer.drain()

                    print(f"[Server] Sent request for function=0x0410 with count={count}")
                    system_log.log_to_redis(f"[Server] Sent request for function=0x0410 with count={count}")

                else:
                    if len(content_data) == 28:
                        parsed = handle_data.parse_28_byte_content(content_data)

                        handle_data.check_in_out_of_bed(parsed)

                        local_time = int(time.time())
                        # Publish the data to MQTT as JSON
                        index_data = {
                            "device_id": client_id,
                            "current_time": local_time,
                        }
                        index_data.update(parsed)  # merges the "parsed" data into index_data

                        json_data = json.dumps(index_data, indent=4)
                        print(json_data)
                        system_log.log_to_redis(json_data)

                        print(f"[Before Publish] Preparing to publish data for device {client_id}")
                        system_log.log_to_redis(f"[Before Publish] Preparing to publish data for device {client_id}")
                        
                        info = mqtt_client.publish(http_client.generate_topic(client_id), json_data, qos=1)
                        
                        if info.rc == mqtt.MQTT_ERR_SUCCESS:
                            print(f"Message successfully sent with {client_id}!")
                            system_log.log_to_redis("Message successfully sent!")
                        else:
                            print(f"Failed to send message with {client_id}:", info.rc)
                            system_log.log_to_redis("Failed to send message")

                    elif len(content_data) == 36:
                        parsed = handle_data.parse_36_byte_content(content_data)

                        handle_data.check_in_out_of_bed(parsed)

                        local_time = int(time.time())
                        # Publish the data to MQTT as JSON
                        index_data = {
                            "device_id": client_id,
                            "current_time": local_time,
                        }
                        index_data.update(parsed)  # merges the "parsed" data into index_data

                        json_data = json.dumps(index_data, indent=4)
                        print(json_data)
                        system_log.log_to_redis(json_data)

                        print(f"[Before Publish] Preparing to publish data for device {client_id}")
                        system_log.log_to_redis(f"[Before Publish] Preparing to publish data for device {client_id}")

                        info = mqtt_client.publish(http_client.generate_topic(client_id), json_data, qos=1)
                        
                        if info.rc == mqtt.MQTT_ERR_SUCCESS:
                            print(f"Message successfully sent with {client_id}!")
                            system_log.log_to_redis("Message successfully sent!")
                        else:
                            print(f"Failed to send message with {client_id}:", info.rc)
                            system_log.log_to_redis("Failed to send message:")

                    else:
                        print(f"[!] content_data length={len(content_data)}, expected 28 or 36.")
                        system_log.log_to_redis(f"[!] content_data length={len(content_data)}, expected 28 or 36.")

            elif function == 0x0410:
                new_id_hex = content_data[-13:].hex()
                ip_to_id_map[client_ip] = new_id_hex

                print(f"[Server] (1) Registered new: IP={client_ip}, ID={new_id_hex}. count={count}")
                system_log.log_to_redis(f"[Server] (1) Registered new: IP={client_ip}, ID={new_id_hex}. count={count}")

    except Exception as e:
        print(f"[Async] Exception for {client_ip}: {e}")
        system_log.log_to_redis(f"[Async] Exception for {client_ip}: {e}")

    finally:
        # Close connection and remove from maps
        writer.close()
        await writer.wait_closed()
        if client_ip in ip_to_id_map:
            del ip_to_id_map[client_ip]

            print(f"[Async] Removed IP={client_ip} from ip_to_id_map.")
            system_log.log_to_redis(f"[Async] Removed IP={client_ip} from ip_to_id_map.")

        if ip_to_writer_map.get(client_ip) is writer:
            del ip_to_writer_map[client_ip]

        print(f"[Async] Ended for {client_ip}.")
        system_log.log_to_redis(f"[Async] Ended for {client_ip}.")

        # Decrease 'count' if close connection
        count = count - 1
        
async def main():
    try:
        if environment_manager.get_auth_token():
            asyncio.create_task(refresh_auth_token())
        
        while True:

            environment_manager.reload_environment()

            if environment.START_SERVER:
                await start_tcp_server()
                
            if environment.STOP_SERVER:
                await stop_tcp_server()
                
            await asyncio.sleep(1)
            
    except asyncio.CancelledError:
        print("[INFO] Tasks were cancelled.")
        system_log.log_to_redis("[INFO] Tasks were cancelled.")

    except KeyboardInterrupt:
        print("\n[INFO] Shutting down gracefully...")
        system_log.log_to_redis("\n[INFO] Shutting down gracefully...")

    finally:
        print("[INFO] Cleaning up before exit...")
        system_log.log_to_redis("[INFO] Cleaning up before exit...")

            