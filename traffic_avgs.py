import arcpy
import pandas as pd
import numpy as np
import json
import os
import arcgis

import secrets

#: Load table from web service using a RecordSet
print('Loading UDOT data...')
record_set = arcpy.RecordSet()
record_set.load(secrets.TABLE_URL)
traffic_dict = json.loads(record_set.JSON)

#: traffic_dict['features'] is the actual table, but is list of nested dicts, all with the single outer key 'attributes'
cleaned_traffic_dict = [t['attributes'] for t in traffic_dict['features']]
traffic_frame = pd.DataFrame.from_dict(cleaned_traffic_dict)

#: Convert dates for .last() operation later
traffic_frame['Date'] = pd.to_datetime(traffic_frame['Date'])

multi_index_df = traffic_frame.set_index(['Station', 'Date'])

station_ids = traffic_frame['Station'].unique()
avgs_df = pd.DataFrame(index=station_ids, columns=['AvgChange7D'], dtype=np.float64)

for i in station_ids:
    working_df = multi_index_df.loc[i, :].last('7D').copy()
    avgs_df.loc[i, 'AvgChange7D'] = working_df['PercentChange'].mean()
    avgs_df.loc[i, 'StartDate'] = str(working_df.index[0])
    avgs_df.loc[i, 'EndDate'] = str(working_df.index[-1])

#: Transpose so that the index becomes the keys and the rows are the values
avgs_dict = avgs_df.T.to_dict()

#: Load features into a feature set
feature_set = arcpy.FeatureSet()
feature_set.load(secrets.FEATURE_URL)

feature_name = 'TrafficChanges'

temp_json_path = os.path.join(arcpy.env.scratchFolder, 'features.json')
temp_fc_path = os.path.join(arcpy.env.scratchGDB, 'features')
sddraft_path = os.path.join(arcpy.env.scratchFolder, f'{feature_name}.sddraft')
sd_path = sddraft_path[:-5]

#: Make sure none of our files already exist
paths = [sddraft_path, sd_path, temp_json_path, temp_fc_path]
for item in paths:
    if arcpy.Exists(item):
        print(f'Deleting {item} prior to use...')
        arcpy.Delete_management(item)

#: Save features to .json, load .json as a feature class
print(f'Saving JSON to {temp_json_path}...')
with open(temp_json_path, 'w') as json_file:
    json_file.write(feature_set.JSON)

print(f'Creating temp feature class {temp_fc_path}...')
arcpy.JSONToFeatures_conversion(temp_json_path, temp_fc_path)

#: Add our new columns.
print('Adding columns...')
columns = [('DetectorStation', 'TEXT'), ('AvgChange7D', 'DOUBLE'), ('StartDate', 'TEXT'), ('EndDate', 'TEXT')]
for col in columns:
    name, dtype = col
    arcpy.AddField_management(temp_fc_path, name, dtype)

#: Update the temp feature class with new averages
print('Updating feature class with new averages...')
fields = ['DetectorStation', 'AvgChange7D', 'StartDate', 'EndDate']
with arcpy.da.UpdateCursor(temp_fc_path, fields) as ucursor:
    for row in ucursor:
        station = row[0]
        if station in avgs_dict:
            row[1] = avgs_dict[station]['AvgChange7D']
            row[2] = avgs_dict[station]['StartDate'].split()[0]
            row[3] = avgs_dict[station]['EndDate'].split()[0]
            ucursor.updateRow(row)

#: Add anchor points for the symbology
print('Adding anchor points...')
anchor_fields = ['DetectorStation', 'AvgChange7D', 'SHAPE@XY']
with arcpy.da.InsertCursor(temp_fc_path, anchor_fields) as icursor:
    null_island = (0,0)
    icursor.insertRow(['AnchorLow', 25, null_island])
    icursor.insertRow(['AnchorHigh', 100, null_island])

#: Overwrite existing AGOL service
print(f'Connecting to AGOL as {secrets.USERNAME}...')
gis = arcgis.gis.GIS('https://www.arcgis.com', secrets.USERNAME, secrets.PASSWORD)
sd_item = gis.content.get(secrets.SD_ITEM_ID)

#: Get project references
#: Assume there's only one map in the project, remove all layers for clean map
print(f'Getting map from {secrets.PROJECT_PATH}...')
project = arcpy.mp.ArcGISProject(secrets.PROJECT_PATH)
covid_map = project.listMaps()[0]
for layer in covid_map.listLayers():
    print(f'Removing {layer} from {covid_map.name}...')
    covid_map.removeLayer(layer)

layer = covid_map.addDataFromPath(temp_fc_path)
project.save()

#: draft, stage, update, publish
print(f'Staging and updating...')
sharing_draft = covid_map.getWebLayerSharingDraft('HOSTING_SERVER', 'FEATURE', feature_name, [layer])
sharing_draft.exportToSDDraft(sddraft_path)
arcpy.server.StageService(sddraft_path, sd_path)
sd_item.update(data=sd_path)
sd_item.publish(overwrite=True)

#: Update item description
print('Updating item description...')
feature_item = gis.content.get(secrets.FEATURES_ITEM_ID)
start_date = avgs_dict[station]['StartDate'].split()[0]
end_date = avgs_dict[station]['EndDate'].split()[0]
description = f'Traffic data obtained from UDOT; updates occur every morning. Data currently reflects traffic from {start_date} to {end_date}.'
feature_item.update(item_properties={'description': description})

#: Cleanup
to_delete = [sddraft_path, sd_path, temp_json_path, temp_fc_path]
for item in to_delete:
    if arcpy.Exists(item):
        print(f'Deleting {item} at end of script...')
        arcpy.Delete_management(item)
