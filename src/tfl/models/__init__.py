# Direct imports from submodules to avoid circular dependencies

# Common
from tfl.models.json.common.base import TflModel
from tfl.models.json.common.mode import Mode
from tfl.models.json.common.mode_id import ModeId

# Journey
from tfl.models.json.journey.crowding_journey import Crowding
from tfl.models.json.journey.disambiguation import Disambiguation
from tfl.models.json.journey.disambiguation_option import DisambiguationOption
from tfl.models.json.journey.disambiguation_result import DisambiguationResult
from tfl.models.json.journey.fare import Fare
from tfl.models.json.journey.instruction import Instruction
from tfl.models.json.journey.instruction_step import InstructionStep
from tfl.models.json.journey.journey import Journey
from tfl.models.json.journey.journey_results import JourneyResults
from tfl.models.json.journey.journey_vector import JourneyVector
from tfl.models.json.journey.leg import Leg
from tfl.models.json.journey.obstacle import Obstacle
from tfl.models.json.journey.path_attribute import PathAttribute
from tfl.models.json.journey.path_journey import Path
from tfl.models.json.journey.route_option import RouteOption
from tfl.models.json.journey.search_criteria import SearchCriteria

# Line
# Note: Line and LineStatus are intentionally from line_model,
# which takes precedence over identically-named types in journey_results.
from tfl.models.json.line.disruption import Disruption
from tfl.models.json.line.line_crowding import LineCrowding
from tfl.models.json.line.line_disruption import LineDisruption
from tfl.models.json.line.line_group import LineGroup
from tfl.models.json.line.line_info import LineInfo
from tfl.models.json.line.line_mode_group import LineModeGroup
from tfl.models.json.line.line_model import Line, LineList, LinesRoutesResponse
from tfl.models.json.line.line_route_section import LineRouteSection
from tfl.models.json.line.line_service_type import LineServiceType
from tfl.models.json.line.line_service_type_info import LineServiceTypeInfo
from tfl.models.json.line.line_status import LineStatus
from tfl.models.json.line.line_status_disruption import LineStatusDisruption
from tfl.models.json.line.line_status_validity_period import LineStatusValidityPeriod
from tfl.models.json.line.matched_route import MatchedRoute
from tfl.models.json.line.route_section import RouteSection
from tfl.models.json.line.validity_period import ValidityPeriod

# Stop Point
from tfl.models.json.stop_point.additional_properties import AdditionalProperties
from tfl.models.json.stop_point.place import Place
from tfl.models.json.stop_point.stop_point_detail import StopPointDetail, StopPointList
from tfl.models.json.stop_point.stop_point_journey import StopPoint
from tfl.models.json.stop_point.stop_point_line import StopPointLine
from tfl.models.json.stop_point.stop_point_search_match import StopPointSearchMatch
from tfl.models.json.stop_point.stop_point_search_response import (
    StopPointSearchResponse,
)
from tfl.models.json.stop_point.stop_points_response import StopPointsResponse

# Timetable
from tfl.models.json.timetable.crowding import Crowding as TimetableCrowding
from tfl.models.json.timetable.interval import Interval
from tfl.models.json.timetable.known_journey import KnownJourney
from tfl.models.json.timetable.passenger_flow import PassengerFlow
from tfl.models.json.timetable.period import Period
from tfl.models.json.timetable.schedule import Schedule
from tfl.models.json.timetable.service_frequency import ServiceFrequency
from tfl.models.json.timetable.station_interval import StationInterval
from tfl.models.json.timetable.station_stop import StationStop
from tfl.models.json.timetable.timetable_disambiguation import TimetableDisambiguation
from tfl.models.json.timetable.timetable_disambiguation_option import (
    TimetableDisambiguationOption,
)
from tfl.models.json.timetable.timetable_model import Timetable
from tfl.models.json.timetable.timetable_response import TimetableResponse
from tfl.models.json.timetable.timetable_route import TimetableRoute
from tfl.models.json.timetable.train_loading import TrainLoading
from tfl.models.json.timetable.twenty_four_hour_clock_time import (
    TwentyFourHourClockTime,
)

# XML Accessibility
from tfl.models.xml.accessibility.booking_hall_to_platform import BookingHallToPlatform
from tfl.models.xml.accessibility.contact_details import ContactDetails
from tfl.models.xml.accessibility.entrance import Entrance
from tfl.models.xml.accessibility.entrance_to_booking_hall import EntranceToBookingHall
from tfl.models.xml.accessibility.entrances import Entrances
from tfl.models.xml.accessibility.facilities import Facilities
from tfl.models.xml.accessibility.facility import Facility
from tfl.models.xml.accessibility.opening_hour import OpeningHour
from tfl.models.xml.accessibility.opening_hours import OpeningHours
from tfl.models.xml.accessibility.platform_to_train import PlatformToTrain
from tfl.models.xml.accessibility.serving_lines import ServingLines
from tfl.models.xml.accessibility.time_interval import TimeInterval
from tfl.models.xml.accessibility.time_intervals import TimeIntervals
from tfl.models.xml.accessibility.zones import Zones

# XML KML
from tfl.models.xml.kml.attribution import Attribution
from tfl.models.xml.kml.header import Header
from tfl.models.xml.kml.icon import Icon
from tfl.models.xml.kml.icon_style import IconStyle
from tfl.models.xml.kml.placemark import Placemark
from tfl.models.xml.kml.point import Point
from tfl.models.xml.kml.root import Root
from tfl.models.xml.kml.station import Station
from tfl.models.xml.kml.stations import Stations
from tfl.models.xml.kml.style import Style

__all__ = [
    "AdditionalProperties",
    "Attribution",
    "BookingHallToPlatform",
    "ContactDetails",
    "Crowding",
    "Disambiguation",
    "DisambiguationOption",
    "DisambiguationResult",
    "Disruption",
    "Entrance",
    "EntranceToBookingHall",
    "Entrances",
    "Facilities",
    "Facility",
    "Fare",
    "Header",
    "Icon",
    "IconStyle",
    "Instruction",
    "InstructionStep",
    "Interval",
    "Journey",
    "JourneyResults",
    "JourneyVector",
    "KnownJourney",
    "Leg",
    "Line",
    "LineCrowding",
    "LineDisruption",
    "LineGroup",
    "LineInfo",
    "LineList",
    "LineModeGroup",
    "LineRouteSection",
    "LineServiceType",
    "LineServiceTypeInfo",
    "LineStatus",
    "LineStatusDisruption",
    "LineStatusValidityPeriod",
    "LinesRoutesResponse",
    "MatchedRoute",
    "Mode",
    "ModeId",
    "Obstacle",
    "OpeningHour",
    "OpeningHours",
    "PassengerFlow",
    "Path",
    "PathAttribute",
    "Period",
    "Place",
    "Placemark",
    "PlatformToTrain",
    "Point",
    "Root",
    "RouteOption",
    "RouteSection",
    "Schedule",
    "SearchCriteria",
    "ServiceFrequency",
    "ServingLines",
    "Station",
    "StationInterval",
    "StationStop",
    "Stations",
    "StopPoint",
    "StopPointDetail",
    "StopPointLine",
    "StopPointList",
    "StopPointSearchMatch",
    "StopPointSearchResponse",
    "StopPointsResponse",
    "Style",
    "TflModel",
    "TimeInterval",
    "TimeIntervals",
    "Timetable",
    "TimetableCrowding",
    "TimetableDisambiguation",
    "TimetableDisambiguationOption",
    "TimetableResponse",
    "TimetableRoute",
    "TrainLoading",
    "TwentyFourHourClockTime",
    "ValidityPeriod",
    "Zones",
]
