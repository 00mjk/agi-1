import json
import os, errno

import boto3
import subprocess
import dpath.util
import requests
import time

help_generic = """
Launch AGIEF. Optionally run experiments (including parameter sweep) and optionally run on AWS ECS.
- Uses the version of code in $AGI_HOME
- Uses the experiment 'run' folder specified in $AGI_RUN_HOME
- Exports the experiment data (if running an experiment)
- See README.md for installation instructions

The script does the following (lines marked AWS are relevant for operation on AWS):
- (AWS) launch ec2 container instance
- (AWS) sync $AGI_HOME folder (excluding source), and $AGI_RUN_HOME folder to the ec2 instance
- launch framework
- (AWS) run the ECS task, which launches the framework, but does not run the experiment
- sweep parameters as specified in experiment input file, and for each parameter value
- imports the experiment from the data files located in $AGI_RUN_HOME
- update the experiment (it will run till termination)
- exports the experiment to $AGI_RUN_HOME

Assumptions:
- Experiment entity exists, with 'terminated' field.
- The 'variables.sh' system is used, as in the bash scripts.
- The script runs sync-experiment.sh, which relies on the ssh alias ec2-user to ssh into the desired ec2 instance.
The instanceId of the same ec2 instance needs to be specified as a parameter when running the script
(there is a default value).
--> these must match  (TODO: to be improved in the future)

"""


def setup_aws(instanceId):
    print "....... starting ec2"
    ec2 = boto3.resource('ec2')
    instance = ec2.Instance(instanceId)
    response = instance.start()

    if log: print "LOG: Start response: ", response

    instance.wait_until_running()

    print "....... syncing files to ec2 container instance"
    subprocess.call(["../aws-ecs/ecs-sync-experiment.sh"])


def close_aws(instanceid):
    ec2 = boto3.resource('ec2')
    instance = ec2.Instance(instanceid)
    response = instance.stop()

    if log:
        print "LOG: stop ec2: ", response


# launch AGIEF on AWS
# hang till framwork is up and running
def launch_framework_aws(task_name, baseurl):
    print "....... launching framework on AWS"
    experiments_aws_setup(task_name)
    wait_framework_up(baseurl)


# launch AGIEF on locally
# hang till framework is up and running
def launch_framework_local(baseurl, main_class=""):
    print "....... launching framework locally"
    cmd = "../node_coordinator/run.sh -m " + main_class;
    subprocess.Popen(cmd,
                     shell=True,
                     stdout=subprocess.PIPE,
                     stderr=subprocess.STDOUT)
    wait_framework_up(baseurl)


def wait_framework_up(baseurl):
    print "....... wait till framework has started at = " + baseurl

    version = "** could not parse version number **"
    while True:
        try:
            response = requests.get(baseurl + '/version')
            if log:
                print "LOG: response = ", response

            responseJson = response.json()
            if 'version' in responseJson:
                version = responseJson['version']
            break
        except requests.ConnectionError:
            time.sleep(1)
            print "  - no connection yet ......"

    print "  - framework is up, running version: " + version


def terminate_framework():
    print "...... terminate framework"
    response = requests.get(baseurl + '/stop')

    if log:
        print "LOG: response text = ", response.text


def experiments_aws_setup(task_name):
    print "....... syncing files to ec2 container instance to " \
          "copy across the new parameter values in config due to sweep"
    subprocess.call(["../aws-ecs/ecs-sync-experiment.sh"])

    print "....... running task on ecs "
    client = boto3.client('ecs')
    response = client.run_task(
        cluster='default',
        taskDefinition=task_name,
        count=1,
        startedBy='pyScript'
    )

    if log:
        print "LOG: ", response


# return when the the config parameter has achieved the value specified
# entity = name of entity, param_path = path to parameter, delimited by '.'
def agief_wait_till_param(baseurl, entity_name, param_path, value):
    while True:
        try:
            r = requests.get(baseurl + '/config', params={'entity': entity_name})
            parameter = dpath.util.get(r.json(), "value." + param_path, '.')
            if parameter == value:
                if log:
                    print "LOG: ... parameter: " + entity_name + "." + param_path + ", has achieved value: " + str(
                        value) + "."
                break
        except requests.exceptions.ConnectionError:
            print "Oops, ConnectionError exception"
        except requests.exceptions.RequestException:
            print "Oops, request exception"

        if log:
            print "LOG: ... parameter: " + entity_name + "." + param_path + ", has not achieved value: " + str(
                value) + ",   wait 2s and try again ........"
        time.sleep(2)  # sleep for n seconds)


# setup the running instance of AGIEF with the input files
def agief_import(entity_filepath=None, data_filepath=None):
    with open(entity_filepath, 'rb') as entity_data_file:
        with open(data_filepath, 'rb') as data_data_file:
            files = {'entity-file': entity_data_file, 'data-file': data_data_file}
            response = requests.post(baseurl + '/import', files=files)
            if log:
                print "LOG: Import entity file, response = ", response
                print "LOG: response text = ", response.text
                print "LOG: url: ", response.url


def agief_run_experiment():
    payload = {'entity': 'experiment', 'event': 'update'}
    response = requests.get(baseurl + '/update', params=payload)
    if log:
        print "LOG: Start experiment, response = ", response

    # wait for the task to finish
    agief_wait_till_param(baseurl, 'experiment', 'terminated', True)  # poll API for 'Terminated' config param


# export_type can be 'entity' or 'data'
def create_folder(filepath):
    if not os.path.exists(os.path.dirname(filepath)):
        try:
            os.makedirs(os.path.dirname(filepath))
        except OSError as exc:  # Guard against race condition
            if exc.errno != errno.EEXIST:
                raise

def agief_export_rootentity(filepath, root_entity, export_type):
    payload = {'entity': root_entity, 'type': export_type}
    response = requests.get(baseurl + '/export', params=payload)
    if log:
        print "LOG: Export entity file, response text = ", response.text

    # write back to file
    output_json = response.json()
    create_folder(filepath)
    with open(filepath, 'w') as data_file:
        data_file.write(json.dumps(output_json, indent=4))


# export the full experiment state from the running instance of AGIEF
# that consists of entity graph and the data
def agief_export_experiment(entity_filepath=None, data_filepath=None):
    agief_export_rootentity(entity_filepath, 'experiment', 'entity')
    agief_export_rootentity(data_filepath, 'experiment', 'data')


# load AGIEF with the input files, run the experiment, then export the experiment
def run_experiment(entity_filepath, data_filepath, output_entity_filepath, output_data_filepath):
    print "....... Run Experiment"
    # agief_import(entity_filepath, data_filepath)
    # agief_run_experiment()
    agief_export_experiment(output_entity_filepath, output_data_filepath)


def modify_parameters(entity_filepath, entity_name, param_path, val):
    print "Modify Parameters: ", entity_filepath, param_path, val

    # open the json
    with open(entity_filepath) as data_file:
        data = json.load(data_file)

    # get the first element in the array with dictionary field "entity-name" = entity_name
    entity = dict()
    for entity_i in data:
        if not entity_i["name"] == entity_name:
            continue
        entity = entity_i
        break

    if not entity:
        print "ERROR: the experiment file (" + entity_filepath + ") did not contain matching entity name (" \
              + entity_name + ") and entity file name in field 'file-entities'."
        print "CANNOT CONTINUE"
        exit()

    # get the config field, and turn it into valid JSON
    configStr = entity["config"]
    configStr = configStr.replace("\\\"", "\"")
    config = json.loads(configStr)

    if log:
        print "LOG: config(t)   = ", config, '\n'

    dpath.util.set(config, param_path, val, '.')
    if log:
        print "LOG: config(t+1) = ", config, '\n'

    # put the escape characters back in the config str and write back to file
    configStr = json.dumps(config)
    configStr = configStr.replace("\"", "\\\"")
    entity["config"] = configStr

    # write back to file
    with open(entity_filepath, 'w') as data_file:
        data_file.write(json.dumps(data))


# return the full path to the inputfile specified by simple filename (AGI_RUN_HOME/input/filename)
def experiment_inputfile(filename):
    return filepath_from_env_variable("input/" + filename, "AGI_RUN_HOME")


# return the full path to the output file specified by simple filename (AGI_RUN_HOME/output/filename)
def experiment_outputfile(filename):
    return filepath_from_env_variable("output/" + filename, "AGI_RUN_HOME")


# run experiments defined in exps_file
def filepath_from_env_variable(filename, path_env):
    variables_file = os.getenv('VARIABLES_FILE', 'variables.sh')
    subprocess.call(["source ../" + variables_file], shell=True)

    cmd = "source ../" + variables_file + " && echo $" + path_env
    output, error = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE).communicate()

    path_from_env = output.strip()
    filepath = os.path.join(path_from_env, filename)
    return filepath


def append_before_ext(filename, text):
    filesplit = os.path.splitext(filename)
    new_filename = filesplit[0] + "_" + text + filesplit[1]
    return new_filename

def run_experiments(exps_file):
    with open(exps_file) as data_exps_file:
        data = json.load(data_exps_file)

    for experiments in data["experiments"]:
        import_files = experiments["import-files"]  # import files dictionary

        if log:
            print "LOG: Import Files Dictionary = "
            print "LOG: ", import_files

        # get experiment filenames, and expand to full path
        entity_file = import_files["file-entities"]
        data_file = import_files["file-data"]

        entity_filepath = experiment_inputfile(entity_file)
        data_filepath   = experiment_inputfile(data_file)

        if log:
            print "LOG: Entity file full path = " + entity_filepath

        if not os.path.isfile(entity_filepath):
            print "ERROR: The entity file " + entity_file + ", at path " + entity_filepath + ", does not exist.\nCANNOT CONTINUE."
            exit()

        for param_sweep in experiments["parameter-sweeps"]:
            entity_name = param_sweep["entity-name"]
            param_path = param_sweep["parameter-path"]
            # exp_type = param_sweep["val-type"]
            val_begin = param_sweep["val-begin"]
            val_end = param_sweep["val-end"]
            val_inc = param_sweep["val-inc"]

            if log:
                print "LOG: Parameter Sweep Dictionary"
                print "LOG: ", param_sweep

            val = val_begin
            while val <= val_end:
                val += val_inc
                modify_parameters(entity_filepath, entity_name, param_path, val)

                short_descr = param_path + "=" + str(val)

                new_entity_file = append_before_ext(entity_file, short_descr)
                output_entity_filepath = experiment_outputfile(new_entity_file)

                new_data_file = append_before_ext(data_file, short_descr)
                output_data_filepath = experiment_outputfile(new_data_file)

                run_experiment(entity_filepath, data_filepath, output_entity_filepath, output_data_filepath)


def getbaseurl(host, port):
    return 'http://' + host + ':' + port


def generate_input_files_locally():
    launch_framework_local(baseurl, args.main_class)

    entity_filepath = experiment_inputfile("entity.json")
    data_filepath = experiment_inputfile("data.json")
    agief_export_experiment(entity_filepath, data_filepath)


if __name__ == '__main__':
    import argparse
    from argparse import RawTextHelpFormatter

    parser = argparse.ArgumentParser(description=help_generic, formatter_class=RawTextHelpFormatter)

    # launch framework only, or launch and run experiments
    parser.add_argument('--mode_gen_input', dest='main_class', required=False,
                        help='Mode Generate Input Files: you must provide the Main class to run, that defines the '
                             'experiment, before exporting the experimental input files entities.json and data.json. '
                             'If this option is specified, it will just generate input files and terminate.')

    # launch framework only, or launch and run experiments
    parser.add_argument('--exps', dest='exps_file', required=False,
                        help='A file that defines the experiments to run (json format). '
                             'If not provided, just launch framework.')

    # how to reach the framework
    parser.add_argument('--host', dest='host', required=False,
                        help='Host where the framework will be running (default=%(default)s).')
    parser.add_argument('--port', dest='port', required=False,
                        help='Port where the framework will be running (default=%(default)s).')

    # run on aws, keep it running or shut it down afterwards
    parser.add_argument('--aws', dest='aws', action='store_true',
                        help='Use this flag to run on AWS. Then InstanceId and Task need to be specified')
    parser.add_argument('--keep_running', dest='keep_running', action='store_true',
                        help='Use this flag to keep the framework running (and AWS instances and ecs tasks if running '
                             'remotely)')
    parser.add_argument('--instanceid', dest='instanceid', required=False,
                        help='Instance ID of the ec2 container instance (default=%(default)s).')
    parser.add_argument('--task_name', dest='task_name', required=False,
                        help='The name of the ecs task (default=%(default)s).')
    parser.add_argument('--logging', dest='logging', action='store_true', help='Turn logging on.')

    parser.set_defaults(logging=False)
    parser.set_defaults(aws=False)
    parser.set_defaults(aws_keep_running=False)
    parser.set_defaults(host="localhost")  # c.x.agi.io
    parser.set_defaults(port="8491")
    parser.set_defaults(instanceid="i-06d6a791")
    parser.set_defaults(task_name="mnist-spatial-task:8")
    args = parser.parse_args()

    global log
    log = args.logging
    if log:
        print "LOG: Arguments: ", args

    baseurl = getbaseurl(args.host, args.port)

    if args.main_class:
        generate_input_files_locally()
        exit()

    if args.aws or args.aws_keep_running:
        if not args.instanceid and not args.task_name:
            print "ERROR: You must specify an EC2 Instance ID (--instanceid) " \
                  "and ECS Task Name (--task_name) to run on AWS."
            exit()

    if args.aws:
        setup_aws(args.instanceid)
        launch_framework_aws(args.task_name, baseurl)
    else:
        launch_framework_local(baseurl)

    if args.exps_file:
        run_experiments(args.exps_file)

    if not args.keep_running:
        terminate_framework()

        if args.aws:
            close_aws(args.instanceid)
