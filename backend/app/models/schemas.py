from pydantic import BaseModel

class SSHConnection(BaseModel):
    host: str
    username: str
    password: str
    port: int = 22
