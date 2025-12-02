from dagster import Definitions

from flathunt.defs.roads import roads
from flathunt.defs.roads_and_transport import roads_and_transport
from flathunt.defs.transport import transport

defs = Definitions(assets=[roads, transport, roads_and_transport])
