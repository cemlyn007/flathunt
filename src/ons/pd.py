import csv
import decimal
from typing import Iterable

__all__ = [
    "district_code",
    "sub_district_code",
    "sector_code",
    "assert_valid_postcode",
    "read_london_active_post_code_centroids",
]


PCD_KEY = "PCD"
LAT_KEY = "LAT"
LONG_KEY = "LONG"
DOTERM_KEY = "DOTERM"
OSGRDINDEX_KEY = "OSGRDIND"
USERTYPE_KEY = "USERTYPE"
OSLAUA_KEY = "OSLAUA"


def district_code(post_code: str) -> str:
    return post_code[:3].strip()


def sub_district_code(post_code: str) -> str:
    code = post_code[:4].strip()
    return code


def sector_code(post_code: str) -> str:
    code = post_code[:5].strip()
    return code


def assert_valid_postcode(post_code: str) -> None:
    if len(post_code) < 6 or len(post_code) > 8:
        raise ValueError("Postcode should range from 6 to 8 characters")
    if not all(c.isalnum() or c == " " for c in post_code):
        raise ValueError("Postcode is not all alphanumeric")
    if not post_code[0].isalpha():
        raise ValueError("First character is not alphabetical")
    if not post_code[1].isalnum():
        raise ValueError("Second character is not alphanumeric")
    if not (post_code[2].isalnum() or post_code[2] == " "):
        raise ValueError("Third character is not alphanumeric or space")
    if not (post_code[3].isalnum() or post_code[3] == " "):
        raise ValueError("Forth character is not alphanumeric or space")
    if not post_code[4].isalnum():
        raise ValueError("Fifth character is not alphanumeric")
    if not post_code[5].isalnum():
        raise ValueError("Sixth character is not alphanumeric")
    if len(post_code) > 6 and not post_code[6].isalnum():
        raise ValueError("Seventh character is not alphanumeric")
    if len(post_code) > 7 and not post_code[7].isalnum():
        raise ValueError("Eigth character is not alphanumeric")


def read_london_active_post_code_centroids(
    file_path: str,
) -> Iterable[tuple[str, decimal.Decimal, decimal.Decimal]]:
    """Reads the ONS postcode centroid file and returns a dictionary of postcodes and their coordinates."""
    with open(file_path, "r") as file:
        reader = csv.reader(file)
        header = next(reader)
        pcd_index = _find_key(header, PCD_KEY)
        lat_index = _find_key(header, LAT_KEY)
        long_index = _find_key(header, LONG_KEY)
        doterm_index = _find_key(header, DOTERM_KEY)
        osgrdindex_index = _find_key(header, OSGRDINDEX_KEY)
        usertype_index = _find_key(header, USERTYPE_KEY)
        osla_index = _find_key(header, OSLAUA_KEY)
        for line in reader:
            line = [cell.strip() for cell in line]
            if (
                len(line[doterm_index]) == 0
                and int(line[osgrdindex_index]) != 9
                and int(line[usertype_index]) == 0
                and line[osla_index].startswith("E")
                # E09000001 – E09000033 is London Borough.
                and (9000000 < int(line[osla_index][1:]) < 9000034)
                and (
                    (
                        coordinate := (
                            decimal.Decimal(line[lat_index]),
                            decimal.Decimal(line[long_index]),
                        ),
                    )
                    != (100, 0)
                )
            ):
                yield (
                    line[pcd_index],
                    *coordinate,
                )


def _find_key(header: list[str], key: str) -> int:
    if key in header:
        return header.index(key)
    else:
        key_lower = key.lower()
        if key_lower in header:
            return header.index(key_lower)
        raise KeyError(f"Key '{key}' not found in header.")
