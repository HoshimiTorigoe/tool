import keras
from keras import layers
from keras import models
from keras.layers import Input, DepthwiseConv2D, Conv2D
from keras.models import load_model
from keras.utils.generic_utils import CustomObjectScope, deserialize_keras_object
from keras.layers import deserialize as layer_from_config


import os.path
import h5py
import json
import numpy as np
import tensorflow as tf
from scipy import misc
import re
import cv2 

from keras import backend as K
from keras.backend.tensorflow_backend import set_session
config = tf.ConfigProto()
config.gpu_options.allow_growth = True  # dynamically grow the memory used on the GPU
config.log_device_placement = True  # to log device placement (on which device the operation ran)
                                    # (nothing gets printed in Jupyter, only if you run it standalone)
sess = tf.Session(config=config)
set_session(sess)  # set this TensorFlow session as the default session for Keras


def get_input(layer_name):
	file_regex = "^\d{0,4}_output_"+layer_name+"\.npy"
	output_file=None
	for filename in os.listdir('debug/keras_outputs'):
		if re.match(file_regex, filename):
			output_file = "debug/keras_outputs/" + filename

	if output_file:
		data = np.load(output_file)
	else:
		print('NO INPUT DATA FOUND')	
		# data = misc.imread('image_019.jpg')
		# data = misc.imread('im1.jpg')
		# data = cv2.imread('im1.jpg')
		data = misc.imread('image_019.jpg')
		# data = cv2.rollaxis(data, (368,432))
		data = np.asarray([data])
	return data

def reorder(dims):
	return (dims[1], dims[0], dims[2])


def layer_split(fpga_network, keras_net):
	network_def = keras_net
	# network_def = 'C:\\Alex\\Work\\fpga_perf\\tool\\network\\mobilenet.h5'

	f = h5py.File(network_def, mode='r')
	model_config = f.attrs.get('model_config')
	model_config = json.loads(model_config.decode('utf-8'))

	globs = globals()  # All layers.
	globs['Model'] = models.Model
	globs['Sequential'] = models.Sequential
	custom_objects = {'relu6': keras.applications.mobilenet.relu6,'DepthwiseConv2D': keras.applications.mobilenet.DepthwiseConv2D}

	globs['Conv2D']= layers.Conv2D
	globs['relu6']=keras.applications.mobilenet.relu6
	globs['DepthwiseConv2D']=keras.applications.mobilenet.DepthwiseConv2D
	
	model_load = load_model(network_def, custom_objects=custom_objects)	
	model_load_weights={}
	for layer in model_load.layers:
		model_load_weights[layer.name]=layer.get_weights()
	# model_load1 = keras.models.model_from_config(model_config, custom_objects=custom_objects)  #use the other one for  real weights	
	print('qwerty')
	print('qwerty')
	# model_weights = model_load.get_weights()
	
	fpga_network_layers={}

	i=0
	for layer in fpga_network._layer:
		K.clear_session()

		first_layer = layer.node_in
		last_layer = layer.node_out

		
		name = first_layer._name 
		if name[-6:]=="_point":
			print('pointlayer')
			continue
		
		input_nodes = first_layer._input_nodes
		if len(input_nodes)>1:
			input_dims = []
			for input_node in input_nodes:
				input_dims.append(reorder(input_node._output_dim))
			keras_input = []
			for input_dim in input_dims:
				keras_input.append(Input(shape=input_dim))
		else:
			input_dim = reorder(first_layer._input_dim)
			keras_input = Input(shape=input_dim)

		
		







		if model_load.get_layer(name).__class__.__name__ == 'SeparableConv2D':
			print('SEPCONV')
			sepconv_layer = model_load.get_layer(name)
			sepconv_weights = model_load_weights[name]

			depthconfig=sepconv_layer.get_config()
			pointconfig=sepconv_layer.get_config()
			

			unused_depth_args = ['filters', 'pointwise_initializer', 'pointwise_regularizer', 'pointwise_constraint', 'bias_initializer']
			for arg in unused_depth_args:
				try:
					del depthconfig[arg]
				except:
					pass
			unused_point_args = ['name', 'kernel_size', 'strides', 'depth_multiplier', 'depthwise_initializer', 'pointwise_initializer', 'depthwise_regularizer', 'pointwise_regularizer', 'depthwise_constraint', 'pointwise_constraint', 'bias_initializer']
			for arg in unused_point_args:
				try:
					del pointconfig[arg]
				except:
					pass
			
			with CustomObjectScope({'relu6': relu6}):
				depth_layer = keras.layers.DepthwiseConv2D(**depthconfig)(keras_input)
			depth_model = Model(inputs=keras_input, outputs = depth_layer)
			depth_bias_shape = depth_model.get_weights()[1].shape
			depth_weights = []
			depth_weights.append(sepconv_weights[0])
			depth_weights.append(np.zeros(depth_bias_shape))
			depth_model.set_weights(depth_weights)

			point_name = name+'_point'
			point_layer_fpga = fpga_network._layer[i+1]

			node_layers = []
			node_layers.append(point_layer_fpga.node_in)
			if point_layer_fpga.node_in == point_layer_fpga.node_out:
				pass
			else:
				node_layers.append(point_layer_fpga.node_out)


			point_input = Input(shape=depth_model.output_shape[1:])
			keras_out_layer = point_input
			for node_layer in node_layers:

				if node_layer==point_layer_fpga.node_in:
					with CustomObjectScope({'relu6': relu6}):
						keras_out_layer = Conv2D(name=point_name, kernel_size=(1,1), **pointconfig)(keras_out_layer)
				else:
					node_layer_name = node_layer._name
					try:
						keras_layer = model_load.get_layer(node_layer_name)
					except:
						print('error')
					keras_layer_class = keras_layer.__class__
					keras_layer_config = keras_layer.get_config()
					with CustomObjectScope({'relu6': relu6}):
						keras_out_layer = keras_layer_class(**keras_layer_config)(keras_out_layer)
						# keras_out_layer.set_weights(keras_layer.get_weights())
			
				if node_layer._bn_node:
					sub_layer_name = node_layer._bn_node._name
					keras_layer = model_load.get_layer(sub_layer_name)
					keras_layer_class = keras_layer.__class__
					keras_layer_config = keras_layer.get_config()
					with CustomObjectScope({'relu6': relu6}):
						keras_out_layer = keras_layer_class(**keras_layer_config)(keras_out_layer)
						# keras_out_layer.set_weights(keras_layer.get_weights())

				if node_layer._act_node:
					sub_layer_name = node_layer._act_node._name
					keras_layer = model_load.get_layer(sub_layer_name)
					keras_layer_class = keras_layer.__class__
					keras_layer_config = keras_layer.get_config()
					with CustomObjectScope({'relu6': relu6}):
						keras_out_layer = keras_layer_class(**keras_layer_config)(keras_out_layer)
						# keras_out_layer.set_weights(keras_layer.get_weights())
			point_model = Model(inputs=point_input, outputs = keras_out_layer)
			# point_model.set_weights(sepconv_weights[1:3])


			for keras_model_layer in point_model.layers:
				keras_model_layer_name = keras_model_layer.name
				if keras_model_layer_name==point_name:
					point_model.set_weights(sepconv_weights[1:3])
				else:
					try:
						keras_model_layer_weights = model_load_weights[keras_model_layer_name]
						keras_model_layer.set_weights(keras_model_layer_weights)
					except:
						pass

			input_data=[]
			input_nodes =  layer.layer_in
			for node in input_nodes:
				input_node_name = node.node_in._name
				input_data.append(get_input(input_node_name))

			depth_predict = depth_model.predict(input_data)
			depth_predict.dump('debug/keras_outputs/'+str(i)+'_output_'+name+'.npy')
			depth_model.save('debug/keras_networks/layer_'+str(i)+'_'+name+'.h5')


			point_predict = point_model.predict(depth_predict)
			point_predict.dump('debug/keras_outputs/'+str(i+1)+'_output_'+point_name+'.npy')
			point_model.save('debug/keras_networks/layer_'+str(i+1)+'_'+point_name+'.h5')

			i+=1
			i+=1

		else:
			node_layers = []
			node_layers.append(layer.node_in)
			if layer.node_in == layer.node_out:
				pass
			else:
				node_layers.append(layer.node_out)

			keras_out_layer = keras_input
			for node_layer in node_layers:
				node_layer_name = node_layer._name
				try:
					keras_layer = model_load.get_layer(node_layer_name)
				except:
					print('error')
				keras_layer_class = keras_layer.__class__
				keras_layer_config = keras_layer.get_config()
				with CustomObjectScope({'relu6': relu6}):
					keras_out_layer = keras_layer_class(**keras_layer_config)(keras_out_layer)
					# keras_out_layer.set_weights(keras_layer.get_weights())
			
				if node_layer._bn_node:
					sub_layer_name = node_layer._bn_node._name
					keras_layer = model_load.get_layer(sub_layer_name)
					keras_layer_class = keras_layer.__class__
					keras_layer_config = keras_layer.get_config()
					with CustomObjectScope({'relu6': relu6}):
						keras_out_layer = keras_layer_class(**keras_layer_config)(keras_out_layer)
						# keras_out_layer.set_weights(keras_layer.get_weights())

				if node_layer._act_node:
					sub_layer_name = node_layer._act_node._name
					keras_layer = model_load.get_layer(sub_layer_name)
					keras_layer_class = keras_layer.__class__
					keras_layer_config = keras_layer.get_config()
					with CustomObjectScope({'relu6': relu6}):
						keras_out_layer = keras_layer_class(**keras_layer_config)(keras_out_layer)
						# keras_out_layer.set_weights(keras_layer.get_weights())

			keras_model = Model(inputs = keras_input, outputs = keras_out_layer)
			for keras_model_layer in keras_model.layers:
				keras_model_layer_name = keras_model_layer.name
				try:
					keras_model_layer_weights = model_load_weights[keras_model_layer_name]
					keras_model_layer.set_weights(keras_model_layer_weights)
				except:
					pass


			input_data=[]
			input_nodes =  layer.layer_in
			for node in input_nodes:
				input_node_name = node.node_in._name
				input_data.append(get_input(input_node_name))


			try:
				prediction = keras_model.predict(input_data)
				prediction.dump('debug/keras_outputs/'+str(i)+'_output_'+name+'.npy')
			except:
				print("error")
			

			keras_model.save('debug/keras_networks/layer_'+str(i)+'_'+name+'.h5')
			i+=1

	print('Done.')



def layer_split_old(network_def, network_data, network_type,
									custom_layer):
	print('qwerty')
	print('qwerty')
	import re
	regex = r"^[^/:]*"

	network_def = 'C:\\Alex\\Work\\fpga_perf\\tool\\network\\mobilenet.h5'

	f = h5py.File(network_def, mode='r')
	model_config = f.attrs.get('model_config')
	model_config = json.loads(model_config.decode('utf-8'))

	globs = globals()  # All layers.
	globs['Model'] = models.Model
	globs['Sequential'] = models.Sequential
	custom_objects = {'relu6': keras.applications.mobilenet.relu6,'DepthwiseConv2D': keras.applications.mobilenet.DepthwiseConv2D}

	globs['Conv2D']= layers.Conv2D
	globs['relu6']=keras.applications.mobilenet.relu6
	globs['DepthwiseConv2D']=keras.applications.mobilenet.DepthwiseConv2D
	
	# model_load = load_model(network_def, custom_objects=custom_objects)	
	model_load = keras.models.model_from_config(model_config, custom_objects=custom_objects)  #use the other one for  real weights	
	model_weights = model_load.get_weights()
	
	fpga_network_layers={}


	for i, layer in enumerate(model_config['config']['layers']):
		K.clear_session()
		layer_type = layer['class_name']
		layer_name = layer['name']


		if layer_type in ('BatchNormalization', 'Activation', 'Dropout', 'Reshape') :
			top_layer = layer
			top_layer_type = layer_type
			if layer_type=='Activation':
				if layer['config']['activation']=='softmax':
					fpga_network_layers[layer_name] = [layer]
				else:
					while top_layer_type in ('BatchNormalization', 'Activation', 'Dropout', 'Reshape') :
						top_layer_name = top_layer['inbound_nodes'][0][0][0]
						for l in model_config['config']['layers']:
							if l['name'] == top_layer_name:
								top_layer = l
								break
						top_layer_type = top_layer['class_name']
					# top_layer_name = top_layer['name']
					fpga_network_layers[top_layer_name].append(layer)
			else:
			# search for existing input and output nodes
				while top_layer_type in ('BatchNormalization', 'Activation', 'Dropout', 'Reshape') :
					top_layer_name = top_layer['inbound_nodes'][0][0][0]
					for l in model_config['config']['layers']:
						if l['name'] == top_layer_name:
							top_layer = l
							break
					top_layer_type = top_layer['class_name']
				# top_layer_name = top_layer['name']
				fpga_network_layers[top_layer_name].append(layer)
		else:
			input_shape = model_load.layers[i].input_shape[1:]
			input_layer = Input(shape=input_shape)
			fpga_network_layers[layer_name] = [layer]

	outputs_layer_map = {}
	for key, value in fpga_network_layers.items():
		outputs_layer_map[value[-1]['name']] = key	

	network_outputs={}
	for key, value in list(fpga_network_layers.items())[1:]:
		print(0)
		print(value)
		first_layer_name = value[0]['name']
		input_shape = model_load.get_layer(first_layer_name).input_shape
		input_layer=Input(shape=input_shape[1:])
		print(1)
		network_output = input_layer
		for layer in value:
			layer_config = layer['config']
			layer_method=getattr(keras.layers, layer['class_name'])
			with CustomObjectScope({'relu6': relu6}):
				network_output = layer_method(**layer_config)(network_output)
		print(2)
		model = Model(inputs = input_layer, outputs = network_output)
		print(2.5)
		for layer in model.layers[1:]:
			layer.set_weights(model_load.get_layer(layer.name).get_weights())
		print(3)
		inbound_nodes = []
		inbound_node_names = [x[0] for x in layer['inbound_nodes'][0]]
		for inbound_node_name in inbound_node_names:
			inbound_node = outputs_layer_map[inbound_node_name]
			inbound_node_data = network_outputs['inbound_node']
			inbound_nodes.append(inbound_node_data)
		print(4)
		layer_output = model.predict(inbound_nodes)
		

		










def layer_split1d(network_def, network_data, network_type,
									custom_layer):
	print('qwerty')
	print('qwerty')

	network_def = 'C:\\Alex\\Work\\fpga_perf\\tool\\network\\mobilenet.h5'

	f = h5py.File(network_def, mode='r')
	model_config = f.attrs.get('model_config')
	model_config = json.loads(model_config.decode('utf-8'))

	globs = globals()  # All layers.
	globs['Model'] = models.Model
	globs['Sequential'] = models.Sequential
	custom_objects = {'relu6': keras.applications.mobilenet.relu6,'DepthwiseConv2D': keras.applications.mobilenet.DepthwiseConv2D}

	globs['Conv2D']= layers.Conv2D
	globs['relu6']=keras.applications.mobilenet.relu6
	globs['DepthwiseConv2D']=keras.applications.mobilenet.DepthwiseConv2D
	
	model_load = load_model(network_def, custom_objects=custom_objects)		
	print('qwerty')
	print('qwerty')
	model_weights = model_load.get_weights()
	

	for i, layer in enumerate(model_config['config']['layers']):
		K.clear_session()
		layer_type = layer['class_name']
		layer_config = layer['config']
		layer_method=getattr(keras.layers, layer['class_name'])
		
		if layer_type == 'InputLayer' and i==0:
			layer_config['name']="input"
			input_data = get_input(i, layer_type, shape=model_load.layers[i].input_shape[1:] )
		else:
			input_data = get_input(i, layer_type, shape=model_load.layers[i].input_shape[1:] )
		input_layer=Input(shape=model_load.layers[i].input_shape[1:])
		with CustomObjectScope({'relu6': relu6}):
			output_layer = layer_method(**layer_config)(input_layer)
		network = Model(inputs=input_layer, outputs = output_layer)
		network_weights = network.get_weights()
		if len(network_weights)>0:
			updated_weights=[]
			for w in range(len(network_weights)):
				updated_weights.append(model_weights[0])
				model_weights.pop(0)
			network.set_weights(updated_weights)


		layer_output = network.predict(input_data)
		np.save('output_'+str(i)+'.npy', layer_output)
		print(i)
		print(layer_type)
		print(layer_config)
		network.save('keras_layers/net_'+str(i)+'.h5')


	# zxc= deserialize_keras_object(config,
	#                                 module_objects=globs,
	#                                 custom_objects=custom_objects,
	#                                 printable_module_name='layer')

	# globs['Conv2D']= layers.Conv2D
	# layer1 = model_config['config']['layers'][1]
	# zxc= deserialize_keras_object(layer1, module_objects=globs, custom_objects=custom_objects, printable_module_name='layer')


	# asd = load_model(network_def, custom_objects=custom_objects)


	print('qwerty')
	print('qwerty')




# model_load_outputs =[]
# for layer in model_load.layers:
# 	model_load_outputs.append(layer.output)

# new_model = Model(inputs = model_load.input, outputs = model_load_outputs)
	


