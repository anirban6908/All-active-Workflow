#!/usr/bin/env python2
# -*- coding: utf-8 -*-
"""
Created on Wed Aug  1 16:38:49 2018

@author: anin
"""


import os
import json
import pickle
import errno
import numpy as np


with open('config_file.json') as json_file:  
    data = json.load(json_file)

param_path = data['parameters']
fit_json_path = data['fit_json']

section_map = {'somatic':'soma', 'axonal':'axon', 'apical':'apic',
               'basal':'dend', 'all':'all'}


def save_optimized_params(checkpoint_file,param_names):
    
    checkpoint = pickle.load(open(checkpoint_file, "r"))    
    optimized_individual = [checkpoint['halloffame'][0]]

    param_split_names = [name.split('.')[0] for name in param_names]
    unique = np.unique(np.asarray(param_split_names))
    ix = []
    for u in unique:
        for i,param in enumerate(param_split_names):
            if param == u:
                ix.append(i)
    param_names_arranged = [param_names[k] for k in ix]
    optimized_individual_arranged = [optimized_individual[0][k] for k in ix]
    
    
    fit_json_write_path = './fit_opt.json'
    if not os.path.exists(os.path.dirname(fit_json_write_path)):
        try:
            os.makedirs(os.path.dirname(fit_json_write_path))
        except OSError as exc: # Guard against race condition
            if exc.errno != errno.EEXIST:
                raise
    
    with open(param_path) as json_file:  
        params = json.load(json_file)
    
    optimized_param_dict = {key:optimized_individual_arranged[i] for i,key in \
                            enumerate(param_names_arranged)} 
    
    param_dict_final = {key.split('.')[0]+'.'+
                     section_map[key.split('.')[1]] : optimized_param_dict[key] 
                                        for key in optimized_param_dict.keys()} 
    with open(fit_json_path) as json_file:  
        model_data = json.load(json_file)
        
    param_dict_final_keys = param_dict_final.keys()
    for key in param_dict_final.keys():
        opt_name,opt_sect = key.split('.')
        data_key = 'genome'
        for j in range(len(model_data[data_key])):
            if model_data[data_key][j]['name'] == opt_name and \
                model_data[data_key][j]['section'] == opt_sect:
                model_data[data_key][j]['value'] = str(param_dict_final[key])
                param_dict_final_keys.remove(key)

    
    for key in param_dict_final_keys:
        param_name,sect = key.split('.') 
        model_data['genome'].append(
                {
                  'section' : sect,
                  'name'    : param_name,
                  'value'   : str(param_dict_final[key]),
                  'mechanism': 'HCN'      
                })

    model_data['passive'] = [{'ra' : param_dict_final['Ra.all']}]
    model_data['conditions'][0]['v_init'] = (item['value'] for item in params if \
                                item["param_name"] == "v_init").next()
    
    with open(fit_json_write_path, 'w') as outfile:
        json.dump(model_data, outfile,indent=4)