import arcpy
import pandas as pd
import numpy as np
import json
import os
import tempfile
import arcgis
import getpass

import secrets

#: Load table from web service using a RecordSet
# table_url = 'https://services.arcgis.com/pA2nEVnB6tquxgOW/ArcGIS/rest/services/TMD_DataVolume_gdb/FeatureServer/1'

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

# avgs_df = avgs_df.reset_index()
# avgs_df = avgs_df.rename(columns={'index':'DetectorStation'})
# table_array = avgs_df.to_records()

#: Transpose so that the index becomes the keys and the rows are the values
avgs_dict = avgs_df.T.to_dict()

#: Load features into a structured numpy array
# feature_url = 'https://services.arcgis.com/pA2nEVnB6tquxgOW/ArcGIS/rest/services/TMD_DataVolume_gdb/FeatureServer/0'
feature_set = arcpy.FeatureSet()
feature_set.load(secrets.FEATURE_URL)
# feature_array = arcpy.da.FeatureClassToNumPyArray(feature_set, '*')

#: Save features to .json, load .json as a feature class, insert new info via insertcursor
with tempfile.TemporaryDirectory() as temp_dir:
    temp_json_path = os.path.join(temp_dir, 'features.json')
    with open(temp_json_path, 'w') as json_file:
        json_file.write(feature_set.JSON)

    arcpy.CreateFileGDB(temp_dir, 'temp.gdb')
    temp_fc_path = os.path.join(temp_dir, 'temp.gdb', 'features')
    arcpy.JSONToFeatures_conversion(temp_json_path, temp_fc_path)

    #: Add our new columns.
    columns = [('DetectorStation', 'TEXT'), ('AvgChange7D', 'DOUBLE'), ('StartDate', 'TEXT'), ('EndDate', 'TEXT')]
    for col in columns:
        name, dtype = col
        arcpy.AddField_management(temp_fc_path, name, dtype)

    #: Update the temp feature class with new averages
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
    anchor_fields = ['DetectorStation', 'AvgChange7D', 'SHAPE@XY']
    with arcpy.da.UpdateCursor(temp_fc_path, anchor_fields) as ucursor:
        null_island = (0,0)
        ucursor.insertRow(['Anchor Low', 24, null_island])
        ucursor.insertRow(['Anchor High', 100, null_island])

    #: Overwrite existing AGOL service
    feature_name = 'TrafficChanges'
    sddraft_path = os.path.join(temp_dir, f'{feature_name}.sddraft')
    sd_path = sddraft_path[:-5]

    gis = arcgis.gis.GIS('https://www.arcgis.com', secrets.USERNAME, secrets.PASSWORD)
    sd_item = gis.content.get(secrets.SD_ITEM_ID)

    #: Get project references
    #: Assume there's only one map in the project, remove all layers for clean map
    project = arcpy.mp.ArcGISProject(secrets.PROJECT_PATH)
    covid_map = project.listMaps()[0]
    for layer in covid_map.listLayers():
        print(f'Removing {layer} from {covid_map}...')
        covid_map.removeLayer(layer)
    
    layer = covid_map.listLayers()[0]

    #: draft, stage, update, publish
    sharing_draft = covid_map.getWebLayerSharingDraft('HOSTING_SERVER', 'FEATURE', feature_name, [layer])
    arcpy.server.StageService(sddraft_path, sd_path)
    sd_item.update(data=sd_path)
    sd_item.publish(overwrite=True)



