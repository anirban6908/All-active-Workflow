#!/usr/bin/env python2
# -*- coding: utf-8 -*-
"""
Created on Thu Feb  1 15:50:49 2018

@author: anin
"""

import os
import allensdk
from allensdk.core.cell_types_cache import CellTypesCache
import numpy as np
import errno
import json
import collections


import get_features

junction_potential = -14
temperature = 34
acceptable_stimtypes = [
    'Long Square'
    ]


distinct_id_map = {
    'Long Square': 'LongDC',
    'Ramp': 'Ramp',
    'Square - 2s Suprathreshold': 'LongDCSupra',
    'Ramp to Rheobase': 'RampRheo'
}

optframework_stimtype_map = {
    'Long Square': 'SquarePulse',
    'Ramp': 'RampPulse',
    'Square - 2s Suprathreshold': 'SquarePulse',
    'Ramp to Rheobase': 'RampPulse'
}



section_map = {'soma' : 'somatic',
                         'apic':'apical',
                         'dend':'basal',
                         'axon':'axonal'}



passive_params = ['cm', 'Ra', 'g_pas', 'e_pas']

active_params = {'gbar_Ih' : {
                            'section' : ['soma', 'apic', 'dend'],
                            'mechanism': 'Ih'
                              }
                }

    
def calc_stimparams(time, stimulus_trace):
    """Calculate stimuls start, stop and amplitude from trace"""

    nonzero_indices = np.where(stimulus_trace != 0)[0]

# make sure if the stimulus is ok if there was no input

# if the stimulus is zero
    if not nonzero_indices.any():   # if the list is empty
        # arbitrary values for the no-stimulus response
        stim_start = time[20000]    # after 100ms
        stim_stop = time[-1]        # until the end
        stim_amp_start = 0
        stim_amp_end = 0
    else:
        # if the stimulus is not zero
        stim_start = time[nonzero_indices[0]]
        stim_stop = time[nonzero_indices[-1]]
        stim_amp_start = stimulus_trace[nonzero_indices[0]] * 1e12
        stim_amp_end = stimulus_trace[nonzero_indices[-1]] * 1e12
    tot_duration = time[-1]    
    return stim_start, stim_stop, stim_amp_start, stim_amp_end, tot_duration

def write_stimmap_csv(stim_map, output_dir, stim_sweep_map):
    """Write StimMap.csv"""

    stim_reps_sweep_map = {}

    stimmapreps_csv_content = "DistinctID, StimType, HoldingCurrent, "\
        "Amplitude_Start, Amplitude_End, Stim_Start, Stim_End, Duration, DataPath\n"

    reps = collections.defaultdict(lambda: collections.defaultdict(list))
    for stim_type in stim_map:
        for trace_params in stim_map[stim_type]:
            
            #identify a stimulus with both start and stop values
            # avoids confusion between Ramp and DCs that have the same 
            # start values
            
            amplitude = str(trace_params[3])+'&'+ str(trace_params[6])
            reps[stim_type][amplitude].append(trace_params)
            
    for stim_type in reps:
        for amplitude in reps[stim_type]:

            cumul_params = reps[stim_type][amplitude][0]

            trace_name = cumul_params[0]

            cumul_params[2] = np.mean(
                [rep_params[2] for rep_params in reps
                 [stim_type][amplitude]])

            cumul_params[8] = "|".join(
                rep_params[8] for rep_params in reps[stim_type][amplitude])

            rep_names = [rep_params[0]
                         for rep_params in reps[stim_type][amplitude]]
            rep_sweeps = [stim_sweep_map[rep_name] for rep_name in rep_names]
            stim_reps_sweep_map[trace_name] = rep_sweeps

            tstart_set = set(['.1f' % rep_params[5]
                              for rep_params in reps[stim_type][amplitude]])
            if len(tstart_set) != 1:
                raise Exception(
                    "Stim type %s Amplitude %s don't have equal start "
                    "times: %s" %
                    (stim_type, amplitude.split('&')[0], str(tstart_set)))

            tstop_set = set(['.1f' % rep_params[6]
                             for rep_params in reps[stim_type][amplitude]])
            if len(tstop_set) != 1:
                raise Exception(
                    "Stim type %s Amplitude %s don't have equal stop "
                    "times: %s" %
                    (stim_type, amplitude.split('&')[0], str(tstop_set)))

            stimmapreps_csv_content += ",".join([str(x) for x in cumul_params])
            stimmapreps_csv_content += '\n'

    stimmapreps_csv_filename = os.path.join(output_dir, 'StimMapReps.csv')

    with open(stimmapreps_csv_filename, 'w') as stimmapreps_csv_file:
        stimmapreps_csv_file.write(stimmapreps_csv_content)

    return stim_reps_sweep_map

def write_provenance(
        output_dir,
        nwb_filename,
        stim_sweep_map,
        stim_reps_sweep_map):
    """Writing provenance file"""

    provenance_filename = os.path.join(output_dir, 'provenance.json')

    nwb_md5hash = calculate_md5hash(nwb_filename)

    provenance = {
        'nwb_filename': os.path.abspath(nwb_filename),
        'nwb_md5hash': nwb_md5hash,
        'temperature': temperature,
        'junction_potential': junction_potential,
        'stim_sweep_map': stim_sweep_map,
        'stim_reps_sweep_map': stim_reps_sweep_map}

    with open(provenance_filename, 'w') as provenance_file:
        json.dump(
            provenance,
            provenance_file,
            sort_keys=True,
            indent=4,
            separators=(
                ',',
                ': '))


def calculate_md5hash(filename):
    """Calculate the md5hash of a file"""

    import hashlib
    with open(filename, 'rb') as file_h:
        md5hash = hashlib.md5(file_h.read()).hexdigest()

    return md5hash


def write_specs(output_dir):
    """Writing specs file"""

    specs_content = 'junctionpotential=%.6g\ntemperature=%.6g\n' % \
        (junction_potential, temperature)

    specs_filename = os.path.join(output_dir, 'Specs')
    with open(specs_filename, 'w') as specs_file:
        specs_file.write(specs_content)

def get_cell_data(exten = '.nwb'):

    global dir_list
    dir_list = list()
    v_initial = list()
    os.path.walk(topdir, step, exten)
    nwb_path = [str_path for str_path in dir_list if 'cell_types' in str_path][0]
    nwb_file = allensdk.core.nwb_data_set.NwbDataSet(nwb_path)
    
    stim_map = collections.defaultdict(list)
    stim_sweep_map = {}
    output_dir = os.getcwd() +'/preprocessed'
    
    if not os.path.exists(output_dir):
        try:
            os.makedirs(output_dir)
        except OSError as exc: # Guard against race condition
            if exc.errno != errno.EEXIST:
                raise             
                
    for sweep_number in nwb_file.get_sweep_numbers():
        sweep_data = nwb_file.get_sweep_metadata(sweep_number)
        stim_type = sweep_data['aibs_stimulus_name']

        if stim_type in acceptable_stimtypes:
            sweep = nwb_file.get_sweep(sweep_number)

            start_idx, stop_idx = sweep['index_range']

            stimulus_trace = sweep['stimulus'][start_idx:stop_idx]
            response_trace = sweep['response'][start_idx:stop_idx]

            sampling_rate = sweep['sampling_rate']

            time = np.arange(0, len(stimulus_trace)) / sampling_rate
            trace_name = '%s_%d' % (
            distinct_id_map[stim_type], sweep_number)
            
            stim_start, stim_stop, stim_amp_start, stim_amp_end, tot_duration = calc_stimparams(
                time, stimulus_trace)

            '''
            if abs(stim_amp - sweep_data['aibs_stimulus_amplitude_pa']) \
                    > 0.1:
                if 'Ramp' not in stim_type:
                    raise Exception(
                        "Amplitude doesn't match for Sweep %d, type %s" %
                        (sweep_number, stim_type))
            '''

            

            response_trace_short_filename = '%s.%s' % (trace_name, 'txt')

            response_trace_filename = os.path.join(
                output_dir, response_trace_short_filename)
            

            
            time = time * 1000.0
            response_trace = response_trace * 1000 + junction_potential
            v_initial.append(response_trace[0])
            time_end = time[-1]
            response_end = response_trace[-1]
            
            # downsampling
            time = time[::5]
            response_trace = response_trace[::5]
            if time_end != time[-1]:
                time = np.append(time,time_end)
                response_trace = np.append(response_trace,response_end)
                
            with open(response_trace_filename, 'w') as response_trace_file:
                np.savetxt(response_trace_file,
                              np.transpose([time, response_trace]))

            # Ignore holding current
            holding_current = 0.0  # sweep['bias_current']

            stim_map[distinct_id_map[stim_type]].append([
                trace_name,
                optframework_stimtype_map[stim_type],
                holding_current,
                stim_amp_start /1e12,
                stim_amp_end/1e12,
                stim_start * 1e3,
                stim_stop * 1e3,
                tot_duration * 1e3,
                response_trace_short_filename])

            stim_sweep_map[trace_name] = sweep_number
            
    print 'Writing stimmap.csv ...',

    stim_reps_sweep_map = write_stimmap_csv(stim_map, output_dir, stim_sweep_map)

    print "Done"
    
    write_provenance(
        output_dir,
        nwb_path,
        stim_sweep_map,
        stim_reps_sweep_map)

    write_specs(output_dir)
    v_initial_avg = reduce(lambda x, y: x + y, v_initial) / len(v_initial)
    
    return output_dir, v_initial_avg

topdir = '.'
dir_list = list()

def step(ext, dirname, names):
    ext = ext.lower()
    for name in names:
        if name.lower().endswith(ext):
            dir_list.append(os.path.join(dirname, name)) 
            
def get_cell_morphology(exten = '.swc'):
    global dir_list
    dir_list = list()
    os.path.walk(topdir, step, exten)
    morph_path = [str_path for str_path in dir_list if 'cell_types' in str_path][0]
    return morph_path


def get_cell_model(exten = '.json'):
    global dir_list
    dir_list = list()
    os.path.walk(topdir, step, exten)
    param_path = [str_path for str_path in dir_list if 'fit_opt' in str_path][0]
#    release_param_path = [str_path for str_path in dir_list if 'fit_parameters' in str_path][0]
    return param_path

def get_params(param_path, v_initial_avg):
    model_params = list()
    with open(param_path) as json_file:  
        data = json.load(json_file)
        for key, values in data.iteritems():            
            if key == 'genome':
                for j in range(len(values)):
                    if data[key][j]['name'] in passive_params:
                        iter_dict = {'param_name':data[key][j]['name']}
                        iter_dict['dist_type'] = 'uniform'   
                        iter_dict['sectionlist'] =  data[key][j]['section']   
                        iter_dict['value'] = float(data[key][j]['value'])
                        iter_dict['type'] = 'section'
                        if data[key][j]['mechanism'] != '':
                            iter_dict['mech'] = data[key][j]['mechanism']
                        model_params.append(iter_dict)
       
        for active_param,active_dict in active_params.items():
            for sect in active_dict['section']:
                 iter_dict = {'param_name': active_param}
                 iter_dict['sectionlist'] = section_map[sect]
                 iter_dict['type'] = 'section'
                 iter_dict['dist_type'] = 'uniform'
                 iter_dict['mech'] = active_dict['mechanism']
                 model_params.append(iter_dict)
                
        model_params.append({"param_name": "celsius","type": "global","value": 34})     
        model_params.append({"param_name": "v_init","type": "global","value": v_initial_avg})
    
    return model_params

def write_params_json(model_params,cell_id):
    release_params = dict()
    
    with open('passive_and_Ih_bounds.json','r') as bound_file:
        param_bounds = json.load(bound_file)
    
    for param_dict in model_params:
        param_name = param_dict['param_name']
        
        if param_name in active_params.keys():
            lb,ub = param_bounds[param_name]
            if 'value' in param_dict.keys():
                if lb > param_dict['value']:
                    lb = param_dict['value'] - abs(param_dict['value'])
                elif ub < param_dict['value']:
                    ub = param_dict['value'] + abs(param_dict['value'])
                    
                release_params[param_name + '.' + param_dict['sectionlist']] = param_dict['value']
                del param_dict['value'] 
                
            bound = [lb, ub]
            param_dict['bounds'] =  bound
            mech_param_dict = param_dict.get('mech')
            if mech_param_dict:
                param_dict['type'] = 'range'               
             
            
        elif param_name in passive_params:
             
             lb = param_dict['value'] - .5*abs(param_dict['value'])
             ub = param_dict['value'] +.5*abs(param_dict['value'])
             lb = max(lb, param_bounds[param_name][0])
             ub = min(ub, param_bounds[param_name][1])
             
             bound = [lb, ub]
             param_dict['bounds'] =  bound
#             release_params[param_name + '.' + param_dict['sectionlist']] = param_dict['value']
             del param_dict['value']
    param_write_path = 'config/'+ cell_id + '/parameters.json'
    
    if not os.path.exists(os.path.dirname(param_write_path)):
        try:
            os.makedirs(os.path.dirname(param_write_path))
        except OSError as exc: # Guard against race condition
            if exc.errno != errno.EEXIST:
                raise
                
    with open(param_write_path, 'w') as outfile:
        json.dump(model_params, outfile,indent=4)  
    
        
    return model_params, param_write_path, release_params

def write_mechanisms_json(model_params,cell_id):
    from collections import defaultdict
    model_mechs = defaultdict(list)
    model_mechs['all'].append('pas')
   
    for param_dict in model_params:
        if param_dict['param_name'] in active_params:
            model_mechs[param_dict['sectionlist']].append(param_dict['mech']) 
        
    mechanism_write_path = 'config/'+ cell_id + '/mechanism.json'
    if not os.path.exists(os.path.dirname(mechanism_write_path)):
        try:
            os.makedirs(os.path.dirname(mechanism_write_path))
        except OSError as exc: # Guard against race condition
            if exc.errno != errno.EEXIST:
                raise
    with open(mechanism_write_path, 'w') as outfile:
        json.dump(model_mechs, outfile,indent=4)
    
    
    return mechanism_write_path


def Main(): 
    cell_id = raw_input('Enter the cell_id : ')
    preprocessed_dir,v_initial_avg = get_cell_data()
    morph_path = get_cell_morphology()
    param_path = get_cell_model()
    cell_map = {}
    cell_name = cell_id
    cell_map[cell_name] = \
        {
            'ephys': preprocessed_dir,
            'morphology': morph_path,
            'feature_set_map':'feature_set.json',
            'v_init' : v_initial_avg

        }

    features_write_path,protocols_write_path,all_protocols_write_path = get_features.run(cell_map, 
            force_feature_extraction=True)
    
    model_dir = '.' 
    shell_cmd = 'nrnivmodl ' + model_dir + '/modfiles'
    
    os.system(shell_cmd)
    model_params= get_params(param_path,v_initial_avg)  
    model_params, param_write_path,\
        release_params = write_params_json(model_params,cell_id) 
    
    mechanism_write_path = write_mechanisms_json(model_params,
                                                                  cell_id)
    
    path_dict =  dict()
    path_dict['morphology'] = morph_path
    path_dict['parameters'] = param_write_path
    path_dict['mechanism'] = mechanism_write_path
    path_dict['features'] = features_write_path
    path_dict['protocols'] = protocols_write_path
    path_dict['all_protocols'] = all_protocols_write_path
    path_dict['release_params'] = release_params
    path_dict['fit_json'] = param_path
    
    with open('config_file.json', 'w') as outfile:
        json.dump(path_dict, outfile,indent=4)
    
    
if __name__ == '__main__': 
    Main()