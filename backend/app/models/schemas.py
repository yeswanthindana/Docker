from pydantic import BaseModel

class SSHConnection(BaseModel):
    ip_address: str
    hostname: str
    password: str
    port: int = 22
