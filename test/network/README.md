# About

The goal of this test is to accelarate validation.
This test just compare source code and weight file generated by ths tool with the references.
If the tool outputs the same the test successes, otherwise it fails.

However, the failure does not mean the tool is erroreous since even the generated different from the reference can output the correct result.
Please run an application for the model and check the output.
If the output is correct, please update the reference.

# How to Test
Run the below:

```console
$ test.sh
```

# Mechanism

1. `test.sh` reads a list of model to be tested from `model.list`. Hereafter `<model>` refers to a model name read here.
2. `test.sh` set quantization/transpose\_weight parameters in `<model>/<model>.ini` to be one of [(0, 1), (1, 1)].
3. The DMP Tool generates source code and weight file by `python3 ../convertor.py <model>/<model>.ini`.
4. `test.sh` compared the generated with the references placed in `<model>/ref/q<q>t<t>/`, where `<q>` and `<t>` is quantization and transpose\_weight parameter separately.

# How to Add a New Test

1. Determine the new model name. Hereafter `<model>` refers to this name.
2. Create a directory named `<model>`.
3. Create `<model>/<model>.ini` according to your model. Please be sure to specify the below options in `[OUTPUT}` section:

```INI
[OUTPUT]
output_folder = ../
generated_source = 1
quantization = 0
transpose_weight = 0
```

4. Add `<model>` to `model.list`.
5. Add (Update) references of your model.

## How to Update References
To update reference, run the below command:

```console
$ test.sh --update-ref
```

To update reference of a specified model, run the below:

```console
$ test.sh --update-ref --model <model>  # Please replace <model> with the model name
```