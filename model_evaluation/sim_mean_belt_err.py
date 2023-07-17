#!/usr/bin/env python3

import os
import multiprocessing as mp
import tempfile
from jinja2 import Template
import subprocess
import re
import matplotlib.pyplot as plt
import pickle
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
from tqdm import tqdm

# PARAMETERS
N_WORKERS = 0
VERIFYTA_BINARY = "/Applications/UPPAAL-5.0.0-rc2.app/Contents/Resources/uppaal/bin/verifyta"
CACHE = False

TAU = 50
QUERY = 'Pr [<=TAU] ([] Initializer.init_over imply not ((exists(i : station_t) Station(i).waiting and Belt.check_deadlock(Station(i).input())) or exists(j: station_t) Station(j).error or FlowController.error))'
VARIABLE_PARAMETERS = {
	'CONFIG': range(0, 4),
	'BELT_SPEED': range(1, 6),
	'SENSOR_ERROR': range(1, 30, 5)
}

# PLOT CONFIGURATION
PLOT_OUTPUT_FILE = 'out/plot.png'
CACHE_OUTPUT_FILE = 'out/cache.pkl'
PLOT_LABELS = ['PROCESSING_TIME_MEAN', 'BELT_SPEED', 'SENSOR_ERROR']
PLOT_KEYS = ['PROCESSING_TIME_MEAN', 'BELT_SPEED', 'SENSOR_ERROR']

def start_simulation():

	data = None

	if CACHE and os.path.exists(PLOT_OUTPUT_FILE) and os.path.exists(CACHE_OUTPUT_FILE):
		print('[INFO] Using cached data')
		data = pickle.load(open(CACHE_OUTPUT_FILE, 'rb'))
	
	if data is None:
		print('[INFO] Running simulation')
		data = run_simulation()
		
		with open(CACHE_OUTPUT_FILE, 'wb') as cache_file:
			pickle.dump(data, cache_file)
	
	generate_results_plot(*data)

def generate_results_plot(xvalues, yvalues, zvalues, colorvalues):
	fig = plt.figure()
	ax = fig.add_subplot(111, projection='3d', proj_type='ortho')

	ax.view_init(azim=98, elev=10)
	ax.scatter(xvalues, yvalues, zvalues, c=colorvalues, cmap='RdYlGn', linewidth=0.5, depthshade=False)
	ax.set_xlabel(PLOT_LABELS[0])
	ax.set_ylabel(PLOT_LABELS[1])
	ax.set_zlabel(PLOT_LABELS[2])

	# Add colorbar with coherent range on colorvalues
	scalarMap = plt.cm.ScalarMappable(cmap='RdYlGn')
	scalarMap.set_array(colorvalues)
	fig.colorbar(scalarMap, shrink=0.5, aspect=10)

	print("[DEBUG] Color values: ", min(colorvalues), max(colorvalues))

	plt.savefig(PLOT_OUTPUT_FILE)

def run_simulation():
	# Three axes keys
	xkey, ykey, zkey = PLOT_KEYS
	# "Four" axes values
	xvalues, yvalues, zvalues, colorvalues = [], [], [], []

	pool = mp.Pool(processes=N_WORKERS)

	sim_configuration = list(args_generator())

	print(f'[INFO] Number of simulations: {len(VARIABLE_PARAMETERS[xkey]) * len(VARIABLE_PARAMETERS[ykey]) * len(VARIABLE_PARAMETERS[zkey])}')
		
	for result in tqdm(pool.imap_unordered(run_simulation_configuration, sim_configuration), total=len(sim_configuration)):
		params, probs = result
		xvalues.append(params[xkey])
		yvalues.append(params[ykey])
		zvalues.append(params[zkey])
		colorvalues.append(probs[0])
		#print(f'[DEBUG] Colorvalye: {probs[0]}}')
	
	return xvalues, yvalues, zvalues, colorvalues

def args_generator():
	xkey, ykey, zkey = PLOT_KEYS
	for x in VARIABLE_PARAMETERS[xkey]:
		for y in VARIABLE_PARAMETERS[ykey]:
			for z in VARIABLE_PARAMETERS[zkey]:
				yield {
					xkey: x,
					ykey: y,
					zkey: z
				}

def run_simulation_configuration(params):
	# Create temporary template file with the given parameters
	temp_file = tempfile.NamedTemporaryFile(mode='w', prefix='template_', suffix='.xml')

	# print(f'[INFO] Running simulation with parameters: {params}')
	temp_file.write(generate_template(params))
	temp_file.seek(0)

	query_file = tempfile.NamedTemporaryFile(mode='w', prefix='query_', suffix='.pctl')
	query_file.write(QUERY)
	query_file.seek(0)

	# Run the verifyta binary from UPPAAL
	# cmd configuration:
	cmd = [
		VERIFYTA_BINARY,
		'-C',
		'-S', '0',
		'-H', '32',
		'-E', '0.01',
		temp_file.name,
		query_file.name
	]

	output = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
	if output.returncode != 0:
		print(f'[ERROR] Simulation failed with parameters: {params}')
		print(output.stderr.decode('utf-8'))
		exit(1)

	# Parse the output
	probability_filter = re.compile(r'\[(\d+(?:\.\d+)?(?:e[-+]?\d+)?),(\d+(?:\.\d+)?(?:e[-+]?\d+)?)\]')
	probabilities = probability_filter.findall(output.stdout.decode())

	if not probabilities:
		print(f'[ERROR] Simulation failed with parameters: {params}')
		print(output.stdout.decode('utf-8'))
		exit(1)

	probabilities = [float(p[0]) for p in probabilities]
	
	# If we fall here, the regex failed and we need to adjust it again
	if(len(probabilities) != 2):
		print(f'[ERROR] Simulation failed with parameters: {params}')
		print(output.stdout.decode('utf-8'))
		exit(1)
	return params, probabilities

def generate_template(params):
	with open('digital_twin_stochastic_err_belt.xml', 'r') as template_file:
		template = template_file.read()
	
	var_params = params.copy()
	var_params.update({"TAU": TAU})
	
	jinja_template = Template(template)
	template = jinja_template.render(var_params)

	return template

def main():
	global N_WORKERS
	# Create output directory if it doesn't exist
	if not os.path.exists('out'):
		os.makedirs('out')

	# Get the total number of parallel available workers
	N_WORKERS = os.cpu_count()
	print(f'[INFO] Number of workers: {N_WORKERS}')

	start_simulation()

if __name__ == '__main__':
	main()
