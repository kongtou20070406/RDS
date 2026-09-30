"""Optional, bounded PyTorch Linear/ReLU parameter snapshot export.

The JSON defines a real affine/ReLU model with the exact binary values stored
in the parameters. It does not certify floating-point execution or arbitrary
Python forward behavior. Nothing loads a checkpoint or calls model.forward.
"""
import hashlib
import json
import math

MAX_LAYERS = 256
MAX_PARAMETERS = 1_000_000


class UnsupportedModel(ValueError):
    """No faithful export is defined for this module configuration."""


def binary_rational(value):
    """Encode the exact real value of a finite Python binary float."""
    if type(value) is int:
        numerator, denominator = value, 1
    elif type(value) is float and math.isfinite(value):
        numerator, denominator = value.as_integer_ratio()
    else:
        raise ValueError("A finite binary float or integer is required")
    return str(numerator) if denominator == 1 else f"{numerator}/{denominator}"


def _digest(value):
    raw = json.dumps(value, sort_keys=True, allow_nan=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _reject_hooks(module):
    if any(value for name, value in vars(module).items() if "hooks" in name and name.startswith("_")):
        raise UnsupportedModel("Module hooks are unsupported")
    if any(name in vars(module) for name in ("forward", "__call__", "_call_impl", "_wrapped_call_impl")):
        raise UnsupportedModel("Instance forward/call overrides are unsupported")
    if getattr(module, "_compiled_call_impl", None) is not None:
        raise UnsupportedModel("Compiled call overrides are unsupported")


def export_sequential(model):
    """Return {'model': schema, 'provenance': metadata} without executing it.

    Requires exact nn.Sequential containers, exact nn.Linear/nn.ReLU leaves,
    and eval mode throughout. Nested Sequential is flattened in module order.
    Parameters are detached into CPU clones; subsequent model mutation cannot
    change the returned JSON. PyTorch is imported only when this is called.
    """
    try:
        import torch
    except ImportError as exc:
        raise ImportError("PyTorch is unavailable in this environment; model export requires it") from exc
    nn = torch.nn
    if type(model) is not nn.Sequential:
        raise UnsupportedModel("Only an exact torch.nn.Sequential model is supported")
    global_module = getattr(getattr(nn, "modules", None), "module", None)
    if global_module is not None and any(value for name, value in vars(global_module).items()
                                         if name.startswith("_global_") and "hooks" in name):
        raise UnsupportedModel("Global module hooks are unsupported")
    parametrize = getattr(getattr(nn, "utils", None), "parametrize", None)
    layers, ancestry = [], set()

    def visit(module):
        if type(module) not in (nn.Sequential, nn.Linear, nn.ReLU):
            raise UnsupportedModel(f"Unsupported layer: {type(module).__name__}")
        if id(module) in ancestry:
            raise UnsupportedModel("Cyclic module containers are unsupported")
        if module.training is not False:
            raise UnsupportedModel("Export requires eval mode on every module")
        _reject_hooks(module)
        if parametrize is not None and parametrize.is_parametrized(module):
            raise UnsupportedModel("Parametrized modules are unsupported")
        if type(module) is nn.Sequential:
            if len(ancestry) >= 64:
                raise UnsupportedModel("Export exceeds the 64-container nesting limit")
            if module._parameters or module._buffers:
                raise UnsupportedModel("Sequential containers must not own parameters or buffers")
            ancestry.add(id(module))
            for child in module._modules.values():
                visit(child)
            ancestry.remove(id(module))
        elif type(module) in (nn.Linear, nn.ReLU):
            if module._modules or module._buffers:
                raise UnsupportedModel("Supported leaves must not own submodules or buffers")
            if type(module) is nn.ReLU and module._parameters:
                raise UnsupportedModel("ReLU must not own parameters")
            if type(module) is nn.Linear and set(module._parameters) != {"weight", "bias"}:
                raise UnsupportedModel("Linear must own exactly weight and optional bias")
            layers.append(module)
            if len(layers) > MAX_LAYERS:
                raise UnsupportedModel("Export exceeds the 256-layer snapshot limit")

    visit(model)
    linear_layers = [layer for layer in layers if type(layer) is nn.Linear]
    if not linear_layers:
        raise UnsupportedModel("At least one Linear layer is needed to infer input dimension")
    input_dim = linear_layers[0].in_features
    if type(input_dim) is not int or input_dim <= 0:
        raise UnsupportedModel("Linear dimensions must be positive integers")
    width, parameter_count, exported, dtypes = input_dim, 0, [], []
    supported_dtypes = {torch.float16, torch.bfloat16, torch.float32, torch.float64}

    def snapshot(parameter, shape):
        if type(parameter) is not nn.Parameter:
            raise UnsupportedModel("Only ordinary torch.nn.Parameter tensors are supported")
        if any(name in vars(parameter) for name in ("detach", "cpu", "clone", "tolist",
                                                     "__torch_function__", "__torch_dispatch__")):
            raise UnsupportedModel("Parameter snapshot method/dispatch overrides are unsupported")
        if tuple(parameter.shape) != shape:
            raise UnsupportedModel("Parameter shape does not match declared Linear dimensions")
        if parameter.dtype not in supported_dtypes:
            raise UnsupportedModel("Only real floating-point parameters are supported")
        # Never use state_dict/forward: clone the finite stored coefficients.
        tensor = parameter.detach().cpu().clone()
        if not bool(torch.isfinite(tensor).all().item()):
            raise UnsupportedModel("Nonfinite parameters cannot define a real model")
        return tensor.tolist()

    for layer in layers:
        if type(layer) is nn.ReLU:
            exported.append({"kind": "relu"})
            continue
        if (type(layer.in_features) is not int or type(layer.out_features) is not int
                or layer.in_features != width or layer.out_features <= 0):
            raise UnsupportedModel("Sequential Linear dimensions do not compose")
        width = layer.out_features
        parameter_count += layer.in_features * width + width
        if parameter_count > MAX_PARAMETERS:
            raise UnsupportedModel("Export exceeds the 1000000-parameter snapshot limit")
        weight = snapshot(layer.weight, (width, layer.in_features))
        bias = [0] * width if layer.bias is None else snapshot(layer.bias, (width,))
        exported.append({"kind": "linear", "weight": [[binary_rational(v) for v in row] for row in weight],
                         "bias": [binary_rational(v) for v in bias]})
        dtypes.append({"weight": str(layer.weight.dtype),
                       "bias": None if layer.bias is None else str(layer.bias.dtype)})
    schema = {"input_dim": input_dim, "layers": exported}
    weights = [{"weight": layer["weight"], "bias": layer["bias"]}
               for layer in exported if layer["kind"] == "linear"]
    return {"model": schema,
            "provenance": {"format": "rds.pytorch_sequential.v1", "torch_version": str(torch.__version__),
                           "weights_sha256": _digest(weights), "model_sha256": _digest(schema),
                           "parameter_dtypes": dtypes, "snapshot": "detached_cpu_parameter_values",
                           "semantics": "real_affine_relu_with_exact_binary_parameter_values"}}
