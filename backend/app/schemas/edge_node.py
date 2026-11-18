"""Edge node registration: what the owner and the node itself exchange with the server."""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

EdgeNodeKind = Literal["esp_kit", "linux", "docker", "home_assistant"]
EdgeNodeName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
EdgeKitId = Annotated[str, StringConstraints(pattern=r"^[a-z0-9-]{1,64}$")]
# The node makes this itself: at least 256 bits of randomness, URL-safe.
EdgeNodeToken = Annotated[str, StringConstraints(pattern=r"^fhen_[A-Za-z0-9_-]{43,128}$")]
EdgeRuntimeVersion = Annotated[str, StringConstraints(strip_whitespace=True, max_length=50)]


class EdgeNodePairingCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: EdgeNodeName
    kind: EdgeNodeKind
    kit_id: EdgeKitId | None = None
    # Link an already registered node again instead of creating a new one.
    node_id: int | None = Field(default=None, gt=0)


class EdgeNodePairingResponse(BaseModel):
    pairing_id: int
    pairing_code: str
    expires_at: datetime


class EdgeNodeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    kind: EdgeNodeKind
    kit_id: str | None
    runtime_version: str | None
    created_at: datetime
    last_seen_at: datetime | None
    online: bool


class EdgeNodePairingStatus(BaseModel):
    state: Literal["pending", "activated", "expired"]
    node: EdgeNodeResponse | None = None


class EdgeNodeRename(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: EdgeNodeName


class EdgeNodeActivateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pairing_code: Annotated[str, StringConstraints(min_length=4, max_length=40)]
    node_token: EdgeNodeToken
    node_instance_id: Annotated[str, StringConstraints(max_length=100)] | None = None
    runtime_version: EdgeRuntimeVersion | None = None


class EdgeNodeActivateResponse(BaseModel):
    node_id: int
    name: str


class EdgeNodeHeartbeatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    runtime_version: EdgeRuntimeVersion | None = None


class EdgeNodeHeartbeatResponse(BaseModel):
    node_id: int
    server_time: datetime
