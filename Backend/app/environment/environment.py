# Tail of files that allow to upload
ALLOWED_EXTENSIONS = {".crt", ".private.key", ".cert.pem"}

# Authentication Token
AUTH_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJleHAiOjE3NDIzNzEzODUsInN1YiI6IjMifQ.YN-T0d_JZb04lmf_sVGNyZQpZSinqC4Odc9wqyNYUhI"

#IP for DreamsEdge API
IP_API = "54.252.196.164"

# TCP server information
TCP_SERVER_NAME = "another-tcp-server"

# Deivice name
DEVICE_NAME = "AerosenseDevice"
FACILITY_ID = 11

# Login Information
LOGIN_USERNAME = "admin"
LOGIN_PASSWORD = "123"

# Information USER
USERNAME = "iotteam@devcburst.com"
PASSWORD = "dreamsiot@2025"

AWS_IOT_ENDPOINT = "a1lvnt250s0jlf-ats.iot.ap-southeast-1.amazonaws.com"

# Path to root certificate
root_ca_path = "Backend/app/upload/root-CA.crt"
# Path to private key
private_key_path = "Backend/app/upload/tcp-server.private.key"
# Path to tới certificate  
cert_path = "Backend/app/upload/tcp-server.cert.pem"

MQTT_PORT = 8883  # Port MQTT SSL

# TCP_SERVER
TCP_SERVER_HOST = '0.0.0.0'
TCP_SERVER_PORT = 8899

# Facility list
FACILITY_LIST = {'data': [{'name': 'Bene St.Paul', 'address': 'St.Paul', 'timezone': 'Australia/Sydney', 'tcp_server_name': 'another-tcp-server', 'id': 1, 'created_at': '2025-03-05T12:58:28.316924', 'updated_at': '2025-03-05T12:58:28.316940'}, {'name': 'Rob_Test', 'address': '', 'timezone': 'Australia/Sydney', 'tcp_server_name': 'another-tcp-server', 'id': 6, 'created_at': '2025-03-05T11:31:50.493161', 'updated_at': '2025-03-06T04:04:02.621634'}, {'name': 'facility123', 'address': '123 somewhere', 'timezone': 'UTC+10:00 - AEST - Australian Eastern Standard Time', 'tcp_server_name': None, 'id': 12, 'created_at': '2025-03-19T06:23:55.485983', 'updated_at': '2025-03-19T06:25:17.553137'}, {'name': 'UAT-Facility', 'address': '123 Fake Street', 'timezone': 'UTC+10:00 - AEST - Australian Eastern Standard Time', 'tcp_server_name': 'another-tcp-server', 'id': 11, 'created_at': '2025-03-19T01:06:07.328601', 'updated_at': '2025-03-19T07:05:17.264383'}], 'count': 4}

# Check connection with AWS
START_CHECK_AWS = True
CONNECTION_AWS = True

# Server Status
TCP_SERVER_STATUS = True
AWS_SERVER_STATUS = True

# Control Server
START_SERVER = True
STOP_SERVER = False

# Logging Configuration
MAX_BYTES = 1048576
BACKUP_COUNT = 10


