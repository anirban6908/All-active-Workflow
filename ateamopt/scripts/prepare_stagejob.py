import os,sys
import glob
from ateamopt.nwb_extractor import NWB_Extractor
from ateamopt.model_parameters import AllActive_Model_Parameters
from ateamopt.utils import utility
import ateamopt.optim_config_rules as filter_rules
from ateamopt.jobscript.jobmodule import test_JobModule,\
            PBS_JobModule,Slurm_JobModule,SGE_JobModule,ChainSubJob
import shutil
import logging
import argschema as ags
from ateamopt.optim_schema import Stage_Launch_Config
from collections import defaultdict

logger = logging.getLogger()

def main(args):
    # Job config
    job_config_path = sys.argv[-1]
    stage_jobconfig = args['stage_jobconfig']
    highlevel_job_props = args['highlevel_jobconfig']

    logging.basicConfig(level=highlevel_job_props['log_level'])
    
    job_dir = highlevel_job_props['job_dir']
    path_to_cell_metadata = glob.glob(os.path.join(job_dir,'cell_metadata*.json'))[0]
    stage_tracker_path = os.path.join(job_dir,'stage_tracker_config.json')
    
    cell_metadata=utility.load_json(path_to_cell_metadata)
    cell_id = cell_metadata['cell_id']
    peri_model_id = cell_metadata.get('peri_model_id')
    released_aa_model_id = cell_metadata.get('released_aa_model_id')
    
    
         
    nwb_path = highlevel_job_props['nwb_path']
    all_features_path = highlevel_job_props['all_features_path']
    all_protocols_path = highlevel_job_props['all_protocols_path']    
    
    stage_stimtypes = stage_jobconfig['stage_stimtypes']
    stage_feature_names_path = stage_jobconfig['stage_features']
    param_bounds_path = stage_jobconfig['stage_parameters']
    script_repo_dir = stage_jobconfig.get('script_repo_dir') 
    run_peri_comparison = stage_jobconfig['run_peri_comparison']
    
    filter_rule_func = getattr(filter_rules,stage_jobconfig['filter_rule'])
    all_features = utility.load_json(all_features_path)
    all_protocols = utility.load_json(all_protocols_path)
    
    stage_feature_names = utility.load_json(stage_feature_names_path)['features']
    select_stim_names = []
    for stim_name in all_features.keys():
        if any(stage_stimtype in stim_name for stage_stimtype in \
                                          stage_stimtypes):
            select_stim_names.append(stim_name)
    
    features_dict = defaultdict(lambda: defaultdict(lambda: defaultdict(dict)))
    for stim_name,stim_dict in all_features.items():
        if stim_name in select_stim_names:
            for loc,loc_features in stim_dict.items():
                for feat,val in loc_features.items():
                    if feat in stage_feature_names:
                        features_dict[stim_name][loc][feat] = [val[0],val[1]]
    
    protocols_dict = {proto_key:proto_val for proto_key,proto_val in all_protocols.\
                      items() if proto_key in select_stim_names}
    nwb_handler = NWB_Extractor(cell_id,nwb_path)
    train_features,test_features,train_protocols = filter_rule_func(\
                                           features_dict,protocols_dict)
    train_features_path,test_features_path,train_protocols_path = \
        nwb_handler.write_ephys_features(train_features,test_features,\
                             train_protocols)
    
    
    # Create the parameter bounds for the optimization
    model_params_handler = AllActive_Model_Parameters(cell_id)
    
    model_params,model_params_release= model_params_handler.get_opt_params(param_bounds_path)
    param_write_path,released_aa_param_write_path,released_aa_params=\
                        model_params_handler.write_params_opt(model_params,model_params_release)
    
    model_mechs,model_mechs_release = model_params_handler.get_opt_mechanism(model_params,\
                        model_params_release,param_bounds_path)
    mech_write_path,mech_release_write_path = model_params_handler.write_mechanisms_opt(model_mechs,\
                        model_mechs_release)
    
    props = {}
    if peri_model_id:
        peri_model_path = cell_metadata['model_path_perisomatic']
        peri_params_write_path, peri_mech_write_path = \
                model_params_handler.aibs_peri_to_bpopt(peri_model_path)
        props['released_peri_model'] = peri_params_write_path
        props['released_peri_mechanism'] = peri_mech_write_path
    
    # Config file with all the necessary paths to feed into the optimization
    model_params_handler.write_opt_config_file(param_write_path,
                                  mech_write_path,mech_release_write_path,
                                  train_features_path,test_features_path,
                                  train_protocols_path,
                                  released_aa_params,released_aa_param_write_path,
                                  opt_config_filename=job_config_path,
                                  **props)
    
    # Copy the optimizer scripts in the current directory
    optimizer_script= stage_jobconfig['main_script']
    analysis_script = stage_jobconfig['analysis_script']
    if script_repo_dir:
        optimizer_script_repo = os.path.abspath(os.path.join(script_repo_dir,
                                        optimizer_script))
        optimizer_script_repo = optimizer_script_repo if os.path.exists(optimizer_script_repo)\
                                        else None
    else:
        optimizer_script_repo = None
    optimizer_script_default=utility.locate_script_file(optimizer_script)
    optimizer_script_path = optimizer_script_repo or optimizer_script_default
    stage_cwd = os.getcwd()
    shutil.copy(optimizer_script_path,stage_cwd)
    
    
    next_stage_job_props = utility.load_json(stage_tracker_path)
    
    machine = highlevel_job_props['machine']
    machine_match_patterns = ['hpc-login','aws','cori','bbp5']
    
    next_stage_jobconfig = {}
    try:
        next_stage_jobconfig['stage_jobconfig']=next_stage_job_props.pop(0)
        next_stage_jobconfig['highlevel_jobconfig']=highlevel_job_props
        
    except:
        pass
    
    utility.save_json(stage_tracker_path,next_stage_job_props)
    
    # Create batch jobscript
    if not any(substr in machine for substr in machine_match_patterns):
        testJob = test_JobModule('batch_job.sh',job_config_path=job_config_path)
        
        testJob.script_generator(next_stage_job_config=next_stage_jobconfig)
        chainjobtemplate_path = 'job_templates/chainjob_template.sh'
    elif 'hpc-login' in machine:
        jobtemplate_path = 'job_templates/pbs_jobtemplate.sh'
        batch_job = PBS_JobModule(jobtemplate_path,job_config_path)
        batch_job.script_generator(next_stage_job_config=next_stage_jobconfig)
        
        analysis_job = PBS_JobModule(jobtemplate_path,job_config_path,
                         script_name='analyze_job.sh')
        analysis_job.script_generator(analysis=True)
    elif 'cori' in machine:
        jobtemplate_path = 'job_templates/nersc_slurm_jobtemplate.sh'
        
    elif 'bbp' in machine:
        jobtemplate_path = 'job_templates/bbp_slurm_jobtemplate.sh'
        
    elif 'aws' in machine:
        jobtemplate_path = 'job_templates/sge_jobtemplate.sh'
        
        
    if next_stage_jobconfig:
        
        stage_jobdir = os.path.join(highlevel_job_props['job_dir'],
                        next_stage_jobconfig['stage_jobconfig']['stage_name'])
        
        next_stage_jobconfig_path = os.path.join(stage_jobdir,'stage_job_config.json')
        utility.create_filepath(next_stage_jobconfig_path)
        utility.save_json(next_stage_jobconfig_path,next_stage_jobconfig)
        prepare_jobscript_default=utility.locate_script_file('prepare_stagejob.py')
        analyze_jobscript_default=utility.locate_script_file(analysis_script)
        shutil.copy(prepare_jobscript_default,stage_jobdir)
        shutil.copy(analyze_jobscript_default,stage_jobdir)  
    
        chain_job = ChainSubJob(chainjobtemplate_path,next_stage_jobconfig_path)
        chain_job.script_modifier()

if __name__ == '__main__':
    mod = ags.ArgSchemaParser(schema_type=Stage_Launch_Config)
    main(mod.args)
