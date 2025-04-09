# Flat Hunt
This repository exists for improving the search experience, it has the following benefits:
* It remembers your search criteria
* It remembers what properties you have previously looked at
* It automatically opens new properties for you
* Automatically filters properties by commute durations
* It automatically shows the commute durations for you
* It automatically shows the map for you

# What you'll probably need to do:
1. Create a `locations.json` file that contains the locations you want to compare commute times from a Rightmove property. A small example would be of the following format:
```json
{
    "Big Ben": [
        51.5007,
        -0.1246
    ],
    ...
}
```

2. Create a `search_locations.json` file that contains the locations you want to search for properties in. A small example would be of the following format:
```json
{
    "Barbican Underground Station": "STATION^569",
    "Canada Water Underground Station": "STATION^1721",
    "Angel Underground Station": "STATION^245",
    ...
}
```
Where the values in the dictionary can be obtained by reading the Rightmove URL or by using the `src/rightmove/scripts/update_search_locations.py` script. The script will create a `search_locations.json` file for you, but you can also create it manually if you want to.
