import sys
import urllib.parse


def url(source: tuple[float, float], destination: tuple[float, float]) -> str:
    saddr = ",".join(map(str, source))
    daddr = ",".join(map(str, destination))
    if sys.platform == "darwin":
        parameters = {
            "saddr": saddr,
            "daddr": daddr,
            "dirflg": "r",
        }
        url = "https://maps.apple.com/"
    else:
        parameters = {
            "api": 1,
            "origin": saddr,
            "destination": daddr,
            "travelmode": "transit",
        }
        url = "https://www.google.com/maps/dir/"
    query_string = urllib.parse.urlencode(parameters, doseq=True)
    urlparse = urllib.parse.urlparse(url)
    urlparse = urlparse._replace(query=query_string)
    url = urllib.parse.urlunparse(urlparse)
    return url
