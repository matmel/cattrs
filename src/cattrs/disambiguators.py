"""Utilities for union (sum type) disambiguation."""
from collections import OrderedDict
from functools import reduce
from operator import or_
from re import L
from typing import Any, Callable, Dict, Mapping, Optional, Type

from attr import NOTHING, fields

from cattrs._compat import get_origin


def create_uniq_field_dis_func(
    *classes: Type[Any],
) -> Callable[[Mapping[Any, Any]], Optional[Type[Any]]]:
    """Given attr classes, generate a disambiguation function.

    The function is based on unique fields."""
    if len(classes) < 2:
        raise ValueError("At least two classes required.")
    cls_and_attrs = [
        (cl, set(at.name for at in fields(get_origin(cl) or cl))) for cl in classes
    ]
    if len([attrs for _, attrs in cls_and_attrs if len(attrs) == 0]) > 1:
        raise ValueError("At least two classes have no attributes.")
    # TODO: Deal with a single class having no required attrs.
    # For each class, attempt to generate a single unique required field.
    uniq_attrs_dict: Dict[str, Type] = OrderedDict()
    cls_and_attrs.sort(key=lambda c_a: -len(c_a[1]))

    fallback = None  # If none match, try this.

    for i, (cl, cl_reqs) in enumerate(cls_and_attrs):
        other_classes = cls_and_attrs[i + 1 :]
        if other_classes:
            other_reqs = reduce(or_, (c_a[1] for c_a in other_classes))
            uniq = cl_reqs - other_reqs
            if not uniq:
                m = "{} has no usable unique attributes.".format(cl)
                raise ValueError(m)
            # We need a unique attribute with no default.
            cl_fields = fields(get_origin(cl) or cl)
            for attr_name in uniq:
                if getattr(cl_fields, attr_name).default is NOTHING:
                    break
            else:
                raise ValueError(f"{cl} has no usable non-default attributes.")
            uniq_attrs_dict[attr_name] = cl
        else:
            fallback = cl

    def dis_func(data: Mapping[Any, Any]) -> Optional[Type]:
        if not isinstance(data, Mapping):
            raise ValueError("Only input mappings are supported.")
        for k, v in uniq_attrs_dict.items():
            if k in data:
                return v
        return fallback

    return dis_func


def create_type_name_field_dis_func(
    *classes: Type[Any], type_name_key: str = "type"
) -> Callable[[Mapping[Any, Any]], Optional[Type[Any]]]:
    """Generate a disambiguation function that reads a key holding the type name

    The name of the key is customizable. Optionally a mapping for the type name can be
    given. If the type name passed via the type key is not recognized, the first class
    of the union is returned.
    """
    names_to_cl = {c.__name__: c for c in classes}
    fallback = classes[0]

    def dis_func(data: Mapping[Any, Any]) -> Optional[Type]:
        if not isinstance(data, Mapping):
            raise ValueError("Only input mappings are supported")

        if type_name_key not in data:
            raise ValueError(
                f"Cannot disambiguate union type if key {type_name_key} is not in the "
                "mapping"
            )
        type_name = data[type_name_key]

        if type_name not in names_to_cl:
            return fallback

        return names_to_cl[type_name]

    return dis_func
