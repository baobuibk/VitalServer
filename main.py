import environment
import http_client
import  handle_data

import asyncio
import numpy as np
import json
import ssl
import paho.mqtt.client as mqtt

# Global counter (uint32)
count = np.uint32(0)

# Maps client_ip -> client_id_hex
ip_to_id_map = {}

# Maps client_ip -> current writer (so we can close the old writer if the same IP reconnects)
ip_to_writer_map = {}

# Global MQTT client
mqtt_client = None

async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    global count
    global mqtt_client

    client_address = writer.get_extra_info('peername')
    if not client_address:
        # Some cases where writer.get_extra_info('peername') could return None (if the socket closed quickly)
        print("[handle_client] Could not retrieve peername (client_address)")
        writer.close()
        await writer.wait_closed()
        return

    client_ip = client_address[0]
    print(f"[Async] Handling new client from IP={client_ip}")

    # If an existing writer for this IP exists, close it (enforcing "one IP - one connection")
    if client_ip in ip_to_writer_map:
        old_writer = ip_to_writer_map[client_ip]
        try:
            old_writer.close()
        except:
            pass
        await old_writer.wait_closed()
        print(f"[Async] Closed old connection for IP={client_ip}")

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
                break

            if not data:
                # Client closed the connection
                print(f"[Async] Client {client_ip} disconnected.")
                break

            print(f"Received data (hex): {data.hex()}")
            request_id, function, content_len, content_data = handle_data.parse_packet(data)
            print(f"[Parsed] function=0x{function:04x}, content_len={content_len}, content_data={content_data.hex()}")

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
                else:
                    if len(content_data) == 28:
                        parsed = handle_data.parse_28_byte_content(content_data)
                        print(f"[Parsed 28-byte content from IP={client_ip}, ID={client_id}]")
                        for k, v in parsed.items():
                            print(f"   {k}: {v}")

                        # Publish the data to MQTT as JSON
                        index_data = {"ID": client_id}
                        json_data = json.dumps([index_data, parsed], indent=4)
                        print(json_data)

                        mqtt_client.publish(http_client.generate_topic(client_id), json_data)

                    elif len(content_data) == 36:
                        parsed = handle_data.parse_36_byte_content(content_data)
                        print(f"[Parsed 36-byte content from IP={client_ip}, ID={client_id}]")
                        for k, v in parsed.items():
                            print(f"   {k}: {v}")

                        # Publish the data to MQTT as JSON
                        index_data = {"ID": client_id}
                        json_data = json.dumps([index_data, parsed], indent=4)
                        print(json_data)

                        mqtt_client.publish(http_client.generate_topic(client_id), json_data)

                    else:
                        print(f"[!] content_data length={len(content_data)}, expected 28 or 36.")

            elif function == 0x0410:
                new_id_hex = content_data[-13:].hex()
                ip_to_id_map[client_ip] = new_id_hex
                print(f"[Server] (1) Registered new: IP={client_ip}, ID={new_id_hex}. count={count}")

    except Exception as e:
        print(f"[Async] Exception for {client_ip}: {e}")

    finally:
        # Close connection and remove from maps
        writer.close()
        await writer.wait_closed()
        if client_ip in ip_to_id_map:
            del ip_to_id_map[client_ip]
            print(f"[Async] Removed IP={client_ip} from ip_to_id_map.")
        if ip_to_writer_map.get(client_ip) is writer:
            del ip_to_writer_map[client_ip]
        print(f"[Async] Ended for {client_ip}.")

        # Decrease 'count' if close connection
        count = count - 1

async def main():
    global mqtt_client

    # ---------------- MQTT Setup ----------------
    mqtt_client = mqtt.Client(client_id="AEROSENSEClient")

    # Configure SSL for secure connections to AWS IoT
    mqtt_client.tls_set(ca_certs=environment.root_ca_path,
                   certfile=environment.cert_path,
                   keyfile=environment.private_key_path,
                   tls_version=ssl.PROTOCOL_TLSv1_2)

    # Attempt to connect to AWS
    print(f"Connecting to AWS")
    mqtt_client.connect(environment.AWS_IOT_ENDPOINT, environment.MQTT_PORT, 60)

    # Start a background thread to handle the network loop
    mqtt_client.loop_start()

    facilities = http_client.get_facility_list()
    ret_val = http_client.check_facility(facilities)
    if ret_val == 0:
        unique_name = environment.TCP_SERVER_NAME
        print(f"Selected Facility ID: {http_client.number_of_facility}, Unique Name: {unique_name}")
        http_client.register_tcp_server(http_client.number_of_facility, unique_name)

    # ---------------- TCP Server Setup (asyncio) ----------------
    server = await asyncio.start_server(
        handle_client,
        host = environment.TCP_SERVER_HOST,
        port = environment.TCP_SERVER_PORT
    )

    addrs = ', '.join(str(sock.getsockname()) for sock in server.sockets)
    print(f"[Async] TCP Server is running on {addrs}")

    async with server:
        # Serve requests until the program is stopped
        await server.serve_forever()

if __name__ == '__main__':

    asyncio.run(main())