"""Pydantic models for TfL Line API responses."""

import pydantic

from tfl.models.line_model import Line

# Type adapter for parsing an array of Line directly
LineList = pydantic.TypeAdapter(list[Line])

# Type adapter for parsing the /Line/Route endpoint response
LinesRoutesResponse = pydantic.TypeAdapter(list[Line])
