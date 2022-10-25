import collections
import typing
import inspect

import attr
import pytest

from cattrs import BaseConverter, Converter
from cattrs.errors import UnknownSubclassError, ClassValidationError
from cattrs.gen import (
    _make_class_tree,
    make_dict_structure_fn,
    make_dict_unstructure_fn,
)


@attr.define
class Parent:
    p: int


@attr.define
class Child1(Parent):
    c1: int


@attr.define
class GrandChild(Child1):
    g: int


@attr.define
class Child2(Parent):
    c2: int


@attr.define
class UnionCompose:
    a: typing.Union[Parent, Child1, Child2, GrandChild]


@attr.define
class NonUnionCompose:
    a: Parent


@attr.define
class UnionContainer:
    a: typing.List[typing.Union[Parent, Child1, Child2, GrandChild]]


@attr.define
class NonUnionContainer:
    a: typing.List[Parent]


@attr.define
class CircularA:
    a: int
    other: "typing.List[CircularA]"


@attr.define
class CircularB(CircularA):
    b: int


IDS_TO_STRUCT_UNSTRUCT = {
    "parent-only": (Parent(1), dict(p=1)),
    "child1-only": (Child1(1, 2), dict(p=1, c1=2)),
    "grandchild-only": (GrandChild(1, 2, 3), dict(p=1, c1=2, g=3)),
    "union-compose-parent": (UnionCompose(Parent(1)), dict(a=dict(p=1))),
    "union-compose-child": (UnionCompose(Child1(1, 2)), dict(a=dict(p=1, c1=2))),
    "union-compose-grandchild": (
        UnionCompose(GrandChild(1, 2, 3)),
        dict(a=(dict(p=1, c1=2, g=3))),
    ),
    "non-union-compose-parent": (NonUnionCompose(Parent(1)), dict(a=dict(p=1))),
    "non-union-compose-child": (NonUnionCompose(Child1(1, 2)), dict(a=dict(p=1, c1=2))),
    "non-union-compose-grandchild": (
        NonUnionCompose(GrandChild(1, 2, 3)),
        dict(a=(dict(p=1, c1=2, g=3))),
    ),
    "union-container": (
        UnionContainer([Parent(1), GrandChild(1, 2, 3)]),
        dict(a=[dict(p=1), dict(p=1, c1=2, g=3)]),
    ),
    "non-union-container": (
        NonUnionContainer([Parent(1), GrandChild(1, 2, 3)]),
        dict(a=[dict(p=1), dict(p=1, c1=2, g=3)]),
    ),
}


def _show_source(c: BaseConverter, cl: typing.Type, operation="structure"):
    """
    Utility func to debug failing tests that shows handler functions of given type
    """
    if c.__class__ == BaseConverter:
        # No-op for BaseConverter
        return

    if operation == "structure":
        f = c._structure_func.dispatch(cl)
    elif operation == "unstructure":
        f = c._unstructure_func.dispatch(cl)
    else:
        raise ValueError(f"operation must be structure or unstructure not {operation}")

    print(f"--- Source code for {cl} dispatch ---")
    for line in inspect.getsourcelines(f)[0]:
        print(line)


@pytest.mark.parametrize(
    "struct_unstruct", IDS_TO_STRUCT_UNSTRUCT.values(), ids=IDS_TO_STRUCT_UNSTRUCT
)
def test_structuring_with_inheritance(converter: BaseConverter, struct_unstruct):
    structured, unstructured = struct_unstruct
    do_not_support_subclass_structure = (
        converter.__class__ == Converter and not converter.include_subclasses
    ) or converter.__class__ == BaseConverter
    xfail_msg = (
        "A BaseConverter or a Converter with include_subclasses=False has no support "
        "for structuring subclasses without specifying explicit union types of all "
        "subclasses."
    )

    restructured = converter.structure(unstructured, structured.__class__)
    _show_source(converter, structured.__class__, "structure")
    if do_not_support_subclass_structure and isinstance(
        structured, (NonUnionContainer, NonUnionCompose)
    ):
        pytest.xfail(xfail_msg)
    assert restructured == structured

    if structured.__class__ in {Child1, Child2, GrandChild}:
        _show_source(converter, Parent, "structure")
        if do_not_support_subclass_structure:
            pytest.xfail(xfail_msg)
        assert converter.structure(unstructured, Parent) == structured

    if structured.__class__ == GrandChild:
        _show_source(converter, Child1, "structure")
        assert converter.structure(unstructured, Child1) == structured

    if structured.__class__ in {Parent, Child1, Child2}:
        if converter.detailed_validation and converter.__class__ == Converter:
            exc = ClassValidationError
        else:
            exc = (KeyError, TypeError)
        with pytest.raises(exc):
            converter.structure(unstructured, GrandChild)


def test_structure_non_attr_subclass():
    @attr.define
    class A:
        a: int

    class B(A):
        def __init__(self, a: int, b: int):
            super().__init__(self, a)
            self.b = b

    converter = Converter(include_subclasses=True)
    d = dict(a=1, b=2)
    with pytest.raises(ValueError, match="has no usable unique attributes"):
        converter.structure(d, A)


def test_structure_as_union():
    converter = Converter(include_subclasses=True)
    the_list = [dict(p=1, c1=2)]
    res = converter.structure(the_list, typing.List[typing.Union[Parent, Child1]])
    _show_source(converter, Parent)
    _show_source(converter, Child1)
    assert res == [Child1(1, 2)]


def test_circular_reference():
    c = Converter(include_subclasses=True)
    struct = CircularB(a=1, other=[CircularB(a=2, other=[], b=3)], b=4)
    unstruct = dict(a=1, other=[dict(a=2, other=[], b=3)], b=4)

    res = c.unstructure(struct)
    assert res == unstruct

    res = c.unstructure(struct, CircularA)
    assert res == unstruct

    res = c.structure(unstruct, CircularA)
    assert res == struct


def test_subclass_union_disambiguation():
    converter = Converter(include_subclasses=True)

    def unstructure_with_type_name(cls):
        return make_dict_unstructure_fn(cls, converter, _cattrs_type_name_key="_type")

    converter.register_unstructure_hook_factory(
        lambda c: issubclass(c, Parent), unstructure_with_type_name
    )

    def structure_with_type_name(cls):
        return make_dict_structure_fn(cls, converter, _cattrs_type_name_key="_type")

    converter.register_structure_hook_factory(
        lambda c: issubclass(c, Parent), structure_with_type_name
    )

    nuc = NonUnionCompose(Child1(1, 2))
    unstructured = {"a": {"_type": "Child1", "p": 1, "c1": 2}}
    assert converter.unstructure(nuc) == unstructured
    assert converter.structure(unstructured, NonUnionCompose) == nuc


@pytest.mark.parametrize(
    "struct_unstruct", IDS_TO_STRUCT_UNSTRUCT.values(), ids=IDS_TO_STRUCT_UNSTRUCT
)
def test_unstructuring_with_inheritance(converter: BaseConverter, struct_unstruct):
    structured, unstructured = struct_unstruct
    converter._unstructure_func.clear_cache()

    _show_source(converter, Parent, "unstructure")

    if isinstance(converter, Converter) and not converter.include_subclasses:
        if isinstance(structured, (NonUnionContainer, NonUnionCompose)):
            pytest.xfail("Cannot succeed if include_subclasses is set to False")

    assert converter.unstructure(structured) == unstructured

    if structured.__class__ in {Child1, Child2, GrandChild}:
        if isinstance(converter, Converter) and not converter.include_subclasses:
            pytest.xfail("Cannot succeed if include_subclasses is set to False")
        assert converter.unstructure(structured, unstructure_as=Parent) == unstructured


def test_unstructuring_unknown_subclass():
    @attr.define
    class A:
        a: int

    @attr.define
    class A1(A):
        a1: int

    converter = Converter(include_subclasses=True)
    assert converter.unstructure(A1(1, 2), unstructure_as=A) == {"a": 1, "a1": 2}

    @attr.define
    class A2(A1):
        a2: int

    _show_source(converter, A, "unstructure")

    with pytest.raises(UnknownSubclassError, match="Subclass.*A2.*of.*A1.* is unknown"):
        converter.unstructure(A2(1, 2, 3), unstructure_as=A1)

    with pytest.raises(UnknownSubclassError, match="Subclass.*A2.*of.*A.* is unknown"):
        converter.unstructure(A2(1, 2, 3), unstructure_as=A)


def test_class_tree_generator():
    class P:
        pass

    class C1(P):
        pass

    class C2(P):
        pass

    class GC1(C2):
        pass

    class GC2(C2):
        pass

    tree_c1 = _make_class_tree(C1)
    assert tree_c1 == [C1]

    tree_c2 = _make_class_tree(C2)
    assert tree_c2 == [C2, GC1, GC2]

    tree_p = _make_class_tree(P)
    assert tree_p == [P, C1, C2, GC1, GC2]


def test_gen_hook_priority(converter: BaseConverter):
    """Autogenerated hooks should not take priority over manual hooks."""

    @attr.define
    class A:
        i: int

    @attr.define
    class B(A):
        pass

    # This will generate a hook.
    assert converter.structure({"i": 1}, B) == B(1)

    # Now we register a manual hook for the superclass.
    converter.register_structure_hook(A, lambda o, T: T(o["i"] + 1))

    # This should still work, but using the new hook instead.
    assert converter.structure({"i": 1}, B) == B(2)


@pytest.mark.parametrize(
    "typing_cls", [typing.Hashable, typing.Iterable, typing.Reversible]
)
def test_inherit_typing(converter: BaseConverter, typing_cls):
    """Stuff from typing.* resolves to runtime to collections.abc.*.

    Hence, typing.* are of a special alias type which we want to check if
    cattrs handles them correctly.
    """

    @attr.define
    class A(typing_cls):
        i: int = 0

        def __hash__(self):
            return hash(self.i)

        def __iter__(self):
            return iter([self.i])

        def __reversed__(self):
            return iter([self.i])

    assert converter.structure({"i": 1}, A) == A(i=1)


@pytest.mark.parametrize(
    "collections_abc_cls",
    [collections.abc.Hashable, collections.abc.Iterable, collections.abc.Reversible],
)
def test_inherit_collections_abc(converter: BaseConverter, collections_abc_cls):
    """As extension of test_inherit_typing, check if collections.abc.* work."""

    @attr.define
    class A(collections_abc_cls):
        i: int = 0

        def __hash__(self):
            return hash(self.i)

        def __iter__(self):
            return iter([self.i])

        def __reversed__(self):
            return iter([self.i])

    assert converter.structure({"i": 1}, A) == A(i=1)
