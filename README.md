# traffic-avgs

A quick-and-dirty way to update an AGOL layer with new information from external feature service every day.

traffic-avgs was written to pull data from UDOT-provided feature services that contain daily comparisons of current traffic to pre-COVID-social-distancing daily averages. It then figures out the average percent difference over the last seven days, combines this with geometries, and overwrites an AGOL Hosted Feature Service that is used in webmaps.

It relies on having a Feature Service containing the traffic counter points identified by a station ID and a Feature Service containing a table of the daily traffic numbers. The table should have a column comparing the day's traffic with the average pre-social-distancing traffic for that particular day of the week.

The script also adds two points at Null Island containing values of 25 and 100, which allows us to set the ranges for the symbology in webmaps.

As this is a one-off, quick-and-dirty implementation, many schema-specific details were hard-coded into the script. My apologies to any actual software engineers readidng this script.

## Setup

* Run from an ArcGIS Pro environment- clone a new one or use the default.
  * Requires Python 3 and the arcgis, arcpy, numpy, and pandas libraries.
* Create a Pro project with a single, blank map and save it somewhere accessible by the script.
  * The defaults are fine; it just needs a map to open. It will remove all the layers from the first map in the project, however, so don't use a project you're using for something else.
* Rename `secrets_template.py` to `secrets.py` and provide the needed info.
  * `.gitignore` is set to ignore `secrets.py` — verify this on your local repo.

## Environment

traffic-avgs relies on `arcpy.env.scratchFolder` and `arcpy.env.scratchGDB` for temporary storage space. It will delete any existing files using the filenames used by the script, and will attempt to delete all of it's data after finishing.

## Frequency

The UDOT data are generally updated every morning around 8 or 9 AM Mountain Time. The script can be run at any time (it will always overwrite the target Hosted Feature Service with whatever the latest data is, even if it hasn't changed).
