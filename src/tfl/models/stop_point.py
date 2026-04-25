"""Type adapter for parsing stop point lists."""

import pydantic

from tfl.models.stop_point_detail import StopPointDetail

# Type adapter for parsing an array of StopPointDetail directly
# Use this to parse the response from /StopPoint/Mode/{mode}
StopPointList = pydantic.TypeAdapter(list[StopPointDetail])
