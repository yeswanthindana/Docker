import docker
import paramiko
from fastapi import HTTPException
from app.models.schemas import SSHConnection

def get_docker_client():
    try:
        # Connect to the local Docker daemon
        return docker.from_env()
    except docker.errors.DockerException as e:
        raise HTTPException(status_code=500, detail=f"Failed to connect to Docker daemon: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {str(e)}")

def get_ssh_client(conn: SSHConnection):
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(conn.ip_address, port=conn.port, username=conn.hostname, password=conn.password, timeout=10)
        return client
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"SSH connection failed: {str(e)}")
