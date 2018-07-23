import numpy as np
from bokeh.plotting import *
from bokeh.models import ColumnDataSource
from bokeh.layouts import widgetbox
from bokeh.models.widgets import Button, RadioButtonGroup, Select, Slider
import glob
import re
# import bkserve
# from random import random
from bokeh.layouts import column, row
from bokeh.models import Button
from bokeh.palettes import RdYlBu3
from bokeh.plotting import figure, curdoc
from bokeh.models import HoverTool
from bokeh.models import LinearColorMapper, ColorBar, BasicTicker

def remap(arr, dim):
    if len(dim) == 1:
        return arr
    sub_arrs = []
    for step in range(0, dim[2], 8):
        step_end = dim[2] if step + 8 > dim[2] else step + 8
        sub_arr = arr[dim[0] * dim[1] * step : dim[0] * dim[1] * step_end]
        sub_arr.shape = (dim[1], dim[0], step_end - step)
        sub_arr = np.transpose(sub_arr, axes = (1, 0, 2))
        sub_arrs.append(sub_arr)
    return np.concatenate(tuple(sub_arrs), axis = 2)

def point_rel_difference(p,f):
#     Relative Percent Difference = (x−y) / (|x|+|y|)
    point_diffs = np.subtract(f, p)
    abs_point_sums = np.abs(f)+np.abs(p)
    reldiff = (point_diffs/abs_point_sums)
    reldiff[reldiff!=reldiff] = 0
    return reldiff

def get_layer_data(layer):
    if len(keras_outputs[layer].shape)==1:
        x=keras_outputs[layer].size
        return x, keras_outputs[layer], fpga_outputs[layer]

    elif keras_outputs[layer].shape[1]==1 and keras_outputs[layer].shape[0]==1:
        x=keras_outputs[layer].size
        return x, keras_outputs[layer][0][0], fpga_outputs[layer][0][0]

    else:
        channels = keras_outputs[layer].shape[2]
        k_out = np.rollaxis(keras_outputs[layer], 2)
        f_out = np.rollaxis(fpga_outputs[layer], 2)
        return 0, k_out, f_out

def make_plot(layer, channel):
    TOOLS = "pan,wheel_zoom,box_zoom,reset,save"
    length, keras_data, fpga_data = get_layer_data(layer)
    
    plotgrid=[]


    if length == 0:
        channels = keras_data.shape[0]
        chan_min = channel*40
        chan_max = min((channel*40 + 40),channels)
        width = 8
        height = int(channels/width)+1
        color_mapper = LinearColorMapper(palette="Viridis256", low=-1, high=1)
        
        plots=[]
        for channel in range(chan_min, chan_max):
            print(channel)
            print("onechannel")
            img=point_rel_difference(keras_data[channel] , fpga_data[channel])
            
            img=img[::-1] #image shows upside down by default
            
            p = figure(title=str(channel),x_range=(0, keras_data.shape[1]), y_range=(0, keras_data.shape[2]),toolbar_location="left")
            p.image(image=[img], x=0, y=0, dw=keras_data.shape[1], dh=keras_data.shape[2], color_mapper=color_mapper)
            hover = HoverTool()
            hover.tooltips = [("x", "$x"), ("value", "@image")]
            p.tools.append(hover)
            color_bar = ColorBar(color_mapper=color_mapper, ticker=BasicTicker(),
                     label_standoff=3, border_line_color=None, location=(0,0), width=5)
            p.add_layout(color_bar, 'right')
            plots.append(p)
        print("channelsdone")
        for l in range(0,len(plots),width):
            plotgrid.append(plots[l:l+width])
        
        print("plotgriddonw")
        color_mapper = LinearColorMapper(palette="Viridis256", low=-1, high=1)
        p=gridplot(plotgrid, plot_width=220, plot_height=190, color_mapper=color_mapper, color_bar=color_bar, title=str(layer), toolbar_location="left", webgl=True)
        print("p done")
    else:
        channels=0
        x_vals = np.arange(length)
        source=ColumnDataSource(data=dict(x=x_vals, keras=keras_data, fpga=fpga_data))
        p = figure(tools=TOOLS,title="Layer "+str(layer), plot_width=1200, plot_height=800)
        k_line = p.line('x', 'keras', source=source, legend=dict(value="Keras"), line_color="red", line_width=1)
        f_line = p.line('x', 'fpga', source=source,legend=dict(value="FPGA"), line_color="blue", line_width=1)
        hover = HoverTool()
        hover.tooltips = [("x", "$x{(0)}"), ("keras", "@keras"), ("fpga", "@fpga")]
        p.tools.append(hover)
        plotgrid.append([p])
        p=gridplot(plotgrid)

    return p, channels

def update_plot(attrname, old, new):
    root = curdoc().roots[0]
    layer=int(layerselect.value)
    
    print(old)
    print(new)
    print(layer)
    print(channelselect.value)

    channel=int(channelselect.value)
    p, channels=make_plot(layer,channel)
    print("got p and chans")
    channel_select_range = make_channel_range(channels)
    print("got range")
    channelselect.options = channel_select_range
    print("did options")
    curdoc().add_root(column(row(layerselect, channelselect ), p))
    print("added root")
    curdoc().remove_root(root)
    print("removed root")


def make_channel_range(channels):
    channel_select_range=[]
    for c in range(0,channels,40):
        if (c+39)>channels:
            channel_select_range.append(str(c)+'-'+str(channels))
        else:
            channel_select_range.append(str(c)+'-'+str(c+39))
    return channel_select_range


output_file("test.html")
fpga_folder = "C:/Alex/Work/debug_check/mobilenet/jaguar/fpga_dump"
keras_folder = "C:/Alex/Work/debug_check/mobilenet/jaguar/keras_outputs"

fpga_files = glob.glob(fpga_folder+'/*')
keras_files = glob.glob(keras_folder+'/*')
fpga_regex = "layer_input.bin$"
r=re.compile(fpga_regex)
fpga_files = list(filter(lambda x: not r.search(x), fpga_files))

if len(fpga_files) != len(keras_files):
    print("Number of input files does not match")

keras_outputs = []    
for i in range(len(keras_files)):
    keras_outputs.append(np.load(keras_files[i])[0])


fpga_outputs=[]
for i in range(len(fpga_files)):
    fpga_dump = np.fromfile(fpga_files[i], dtype=np.float16)
    if len(fpga_dump)!=keras_outputs[i].size:
        fpga_dump = np.fromfile(fpga_files[i], dtype=np.float32)
    fpga_dump = remap(fpga_dump, keras_outputs[i].shape)
    fpga_outputs.append(fpga_dump)

keras_length = np.arange(len(keras_outputs))
layer_select_range=[]
for l in keras_length:
    layer_select_range.append(str(l))
layerselect = Select(title="Layer:", value="0", options=layer_select_range)
p, channels=make_plot(0, 0)
channel_select_range = make_channel_range(channels)
channelselect = Select(title="Channels:", value="0", options=channel_select_range)

layerselect.on_change('value', update_plot)
channelselect.on_change('value', update_plot)

curdoc().add_root(column(row(layerselect, channelselect ), p))
# show(column(row(layerselect, channelselect ), p))