"""Script to get feature from abi traces"""

# pylint: disable=R0914, F0401, R0912

import os
import json
import numpy as np
import math
import collections
import errno
import efel

def entries_to_remove(entries, the_dict):
    for key in entries:
        if key in the_dict.keys():
            del the_dict[key]
    return the_dict


def run(cell_map, force_feature_extraction=False,dend_recording = None, record_locations = None,\
                        feature_frac = None, max_spike_proto = 2, max_no_spike_proto = 1):
    """Get feature values"""
    cell_name = cell_map.keys()[0]
    features_json_filename = 'config/'+ cell_name +'/features.json'
    protocols_json_filename = 'config/'+cell_name+'/protocols.json'
    all_protocols_json_filename = 'config/'+cell_name+'/all_protocols.json'
    
    efel.api.reset()
    json_exists = os.path.exists(features_json_filename) or \
                            os.path.exists(protocols_json_filename)

    if json_exists and not force_feature_extraction:
        features_meanstd = load_json(features_json_filename)
    else:
        try:
            os.makedirs(os.path.dirname(features_json_filename))
            os.makedirs(os.path.dirname(protocols_json_filename))
        except OSError as exc: # Guard against race condition
            if exc.errno != errno.EEXIST:
                raise
            
        features_meanstd = collections.defaultdict(
            lambda: collections.defaultdict(
                lambda: collections.defaultdict(dict)))

        cell_stim_map = {}
        cell_provenance_map = {}

        for cell_name in cell_map:
            ephys_location = cell_map[cell_name]['ephys']
            v_init_model = cell_map[cell_name]['v_init']
            cell_provenance_map[cell_name] = load_json(
                os.path.join(
                    ephys_location,
                    'provenance.json'))
#            specs = get_specs(os.path.join(ephys_location, 'Specs'))
            stim_map = get_stim_map(os.path.join(ephys_location, 'StimMapReps.csv'),
                                    dend_recording = dend_recording, locations = record_locations)
            feature_set_map = get_feature_set_map(
                cell_map[cell_name]['feature_set_map'])
            cell_stim_map= stim_map
            training_stim_map = dict()
            
#            spike_protocols = 0
#            no_spike_protocols = 0  

            
            spiking_proto_dict = {}
            non_spiking_proto_dict = {}
            
            for stim_name,stim_params in stim_map.items():
                
                
                if 'Ramp' in stim_name or 'LongDCSupra' in stim_name:
                    continue
                
                print "\n### Getting features from %s of cell %s ###\n" \
                    % (stim_name, cell_name)
                
                
                
                no_Spike = False  #boolean variable to control the inclusion of dendritic features

                # Features for this stimulus
                stim_features = feature_set_map['somatic_features']

                sweeps = []
                for sweep_filename in stim_map[stim_name]['stimuli'][0]['sweep_filenames']:
                    sweep_fullpath = os.path.join(
                        ephys_location,
                        sweep_filename)

                    data = np.loadtxt(sweep_fullpath)
                    time = data[:, 0]
                    voltage = data[:, 1]
                    v_init_cell = voltage[0]
                    v_init_correction = v_init_cell - v_init_model 
                    
                    # Correct LJP
#                    voltage = voltage - specs['junctionpotential']
                    time = time

                    # Prepare sweep for eFEL
                    sweep = {}
                    sweep['T'] = time
                    sweep['V'] = voltage
                    sweep['stim_start'] = [stim_map[stim_name]['stimuli'][0]['delay']]
                    sweep['stim_end'] = [stim_map[stim_name]['stimuli'][0]['stim_end']]
                    sweep['T;location_AIS'] = time
                    sweep['V;location_AIS'] = voltage
                    sweep['stim_start;location_AIS'] = [stim_map[stim_name]['stimuli'][0]['delay']]
                    sweep['stim_end;location_AIS'] = [stim_map[stim_name]['stimuli'][0]['stim_end']]

                    sweeps.append(sweep)

                # Do the actual feature extraction
                feature_results = efel.getFeatureValues(sweeps, stim_features)
                temp_spike_count = 0
                for feature_temp_list in feature_results:
                    if feature_temp_list['mean_frequency']:
                        temp_spike_count += feature_temp_list['mean_frequency'][0]
                
                
                
                if temp_spike_count > 0:                    
                    spiking_proto_dict[stim_name] = stim_params['stimuli'][0]['amp']
                elif temp_spike_count == 0: 
                    stim_features = ['Spikecount']
                    feature_results = efel.getFeatureValues(sweeps, stim_features)
                    
                    non_spiking_proto_dict[stim_name] = stim_params['stimuli'][0]['amp']
#                    if stim_params['stimuli'][0]['amp'] >= 0:
                    if dend_recording:
                        del cell_stim_map[stim_name]['extra_recordings']
                 
                   
                for feature_name in stim_features:
                    # For one feature, a list with values for every repetition
                    feature_values = [np.mean(trace_dict[feature_name])
                                      for trace_dict in feature_results
                                      if trace_dict[feature_name] is not None]
                    if len(feature_values) == 0:
                        if 'AP' in feature_name and not no_Spike: 
                        #if an AP related feature has no values then there was no spike in the trace
                            no_Spike = True 
                        continue
                    elif len(feature_values) == 1:
                        mean = feature_values[0]
                        std = 0.05 * abs(mean)
                    elif len(feature_values) > 1:
                        mean = np.mean(feature_values)
                        std = np.std(feature_values)
                    
                    if std== 0 and len(feature_values) != 1:
                       std = 0.05 * abs(mean)/math.sqrt(len(feature_values)) 
                    
                    if math.isnan(mean) or math.isnan(std):
                    #if an AP related feature has nan values then there was no spike in the trace
                        if 'AP' in feature_name and not no_Spike:
                            no_Spike = True
                        continue
                    if mean == 0:
                        std = 0.05
                    if feature_name in ['voltage_base', 'steady_state_voltage']:
                            mean -= v_init_correction
                    features_meanstd[stim_name]['soma'][
                        feature_name] = [mean , std]
                    
                
                    
                if stim_name in features_meanstd.keys():
                    training_stim_map[stim_name] = cell_stim_map[stim_name]
               
                if dend_recording and not no_Spike:
                    dend_features = feature_set_map['dendritic_features']
                    for dend_feature in dend_features:
                        for i in range(len(record_locations)):
                            mean = feature_frac[dend_feature][i]*features_meanstd[stim_name]['soma'][dend_feature][0]
                            std = features_meanstd[stim_name]['soma'][dend_feature][1]
                           
                            features_meanstd[stim_name]['dend'+str(i+1)][dend_feature] = \
                                                    [mean , std]
                elif dend_recording:    
                    del training_stim_map[stim_name]['extra_recordings']
            
            
#            copy_non_spiking_proto_dict = copy.deepcopy(non_spiking_proto_dict)
#            for key,val in copy_non_spiking_proto_dict.items():
#                if val > min(spiking_proto_dict.values()):
#                    del non_spiking_proto_dict[key]
#                    del features_meanstd[key]
#                    del training_stim_map[key]
                    
                    
            spiking_proto_keys = sorted(spiking_proto_dict,
                            key=spiking_proto_dict.__getitem__)
            first_spiking_proto_key = spiking_proto_keys[0]
            del_spiking_proto_keys = spiking_proto_keys[1:-max_spike_proto]
           
            del_non_spiking_proto_keys = sorted(non_spiking_proto_dict, 
                        key=non_spiking_proto_dict.__getitem__)[:-max_no_spike_proto]
            
            del_proto_keys = del_spiking_proto_keys + del_non_spiking_proto_keys
            features_meanstd = entries_to_remove(del_proto_keys, features_meanstd)
            first_spiking_proto_key_features = features_meanstd[first_spiking_proto_key]['soma']
             
            del_features = [key for key in first_spiking_proto_key_features.keys() \
                            if key not in ['mean_frequency', 'check_AISInitiation']]
            
            training_stim_map = entries_to_remove(del_proto_keys, training_stim_map)
            entries_to_remove(del_features, first_spiking_proto_key_features)
            save_json(features_meanstd, features_json_filename)
            save_json(training_stim_map, protocols_json_filename)
            save_json(cell_stim_map, all_protocols_json_filename)


    return features_json_filename, protocols_json_filename,all_protocols_json_filename


def load_json(filename):
    """Load json file"""

    with open(filename) as file_h:
        return json.load(file_h)


def save_json(content, filename):
    """Load json file"""

    with open(filename, 'w') as file_h:
        return json.dump(
            content,
            file_h,
            sort_keys=True,
            indent=4,
            separators=(
                ',',
                ': '))




def get_stim_map(stim_map_filename, dend_recording = None, locations = None):
    """Get stim map"""

    stim_map = collections.defaultdict(dict)

    with open(stim_map_filename, 'r') as stim_map_file:
        stim_map_content = stim_map_file.read()

    for line in stim_map_content.split('\n')[1:-1]:
        if line is not '':
            stim_name, stim_type, holding_current, amplitude_start, amplitude_end, \
                stim_start, stim_end, duration, sweeps = line.split(',')
            iter_dict= dict()
            iter_dict['type'] = stim_type.strip()
            iter_dict['hypamp'] = 1e9 * float(holding_current)
            iter_dict['amp'] = 1e9 * float(amplitude_start)
            iter_dict['amp_end'] = 1e9 * float(amplitude_end)
            iter_dict['delay'] = float(stim_start)
            iter_dict['duration'] = float(stim_end) - float(stim_start)
            iter_dict['stim_end'] = float(stim_end)
            iter_dict['totduration'] = float(duration)
            iter_dict['sweep_filenames'] = [
                x.strip() for x in sweeps.split('|')]
            
            iter_list = [iter_dict]
            stim_map[stim_name]['stimuli'] = iter_list
            if dend_recording:
                record_list = list()
                for i, loc in enumerate(locations):
                    record_dict = dict()
                    record_dict['var'] = 'v'
                    record_dict['somadistance'] = loc
                    record_dict["seclist_name"] = "apical"
                    record_dict['name'] = 'dend'+ str(i+1)
                    record_dict['type'] = 'somadistance'
                    record_list.append(record_dict)
                stim_map[stim_name]['extra_recordings'] = record_list
    return stim_map


def get_specs(specs_filename):
    """Get specs"""

    specs = {}
    with open(specs_filename, 'r') as specs_file:
        specs_content = specs_file.read()

    for line in specs_content.split('\n')[:-1]:
        var_name, var_value = line.split('=')
        specs[var_name] = float(var_value)

    return specs


def get_feature_set_map(feature_map_filename):
    """Get feature set map"""

    with open(feature_map_filename, 'r') as feature_map_file:
        feature_map = json.load(feature_map_file)

    return feature_map
