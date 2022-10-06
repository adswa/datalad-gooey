from pathlib import Path
from typing import Dict

# this is an import target for all constraints used within gooey
from datalad.support.constraints import (
    AltConstraints,
    Constraint,
    EnsureStr,
    EnsureChoice,
    EnsureNone,
    EnsureBool,
    EnsureInt,
    EnsureRange,
    EnsureListOf,
)
from datalad.distribution.dataset import Dataset


# extension for Constraint from datalad-core
def for_dataset(self, dataset: Dataset) -> Constraint:
    """Return a constraint-variant for a specific dataset context

    The default implementation returns the unmodified, identical
    constraint. However, subclasses can implement different behaviors.
    """
    return self


# patch it in
Constraint.for_dataset = for_dataset


class NoConstraint(Constraint):
    """A contraint that represents no constraints"""
    def short_description(self):
        return ''

    def __call__(self, value):
        return value


class EnsureMapping(Constraint):
    """Ensure a mapping of a key to a value of a specific nature"""

    def __init__(self,
                 key: Constraint,
                 value: Constraint,
                 delimiter: str = ':'):
        """
        Parameters
        ----------
        key:
          Key constraint instance.
        value:
          Value constraint instance.
        delimiter:
          Delimiter to use for splitting a key from a value for a `str` input.
        """
        self._key_constraint = key
        self._value_constraint = value
        self._delimiter = delimiter

    def short_description(self):
        return 'mapping of {} -> {}'.format(
            self._key_constraint.short_description(),
            self._value_constraint.short_description(),
        )

    def __call__(self, value) -> Dict:
        # determine key and value from various kinds of input
        if isinstance(value, str):
            # will raise if it cannot split into two
            key, val = value.split(sep=self._delimiter, maxsplit=1)
        elif isinstance(value, dict):
            if not len(value):
                raise ValueError('dict does not contain a key')
            elif len(value) > 1:
                raise ValueError(f'{value} contains more than one key')
            key, val = value.copy().popitem()
        elif isinstance(value, (list, tuple)):
            if not len(value) == 2:
                raise ValueError('key/value sequence does not have length 2')
            key, val = value

        key = self._key_constraint(key)
        val = self._value_constraint(val)
        return {key: val}

    def for_dataset(self, dataset: Dataset):
        # tailor both constraints to the dataset and reuse delimiter
        return EnsureMapping(
            key=self._key_constraint.for_dataset(dataset),
            value=self._value_constraint.for_dataset(dataset),
            delimiter=self._delimiter,
        )


class EnsureStrOrNoneWithEmptyIsNone(EnsureStr):
    def __call__(self, value):
        if value is None:
            return None
        # otherwise, first the regular str business
        v = super().__call__(value)
        # force to None if empty
        return v if v else None


class EnsureDatasetSiblingName(EnsureStr):
    def __init__(self, allow_none=False):
        # basic protection against an empty label
        super().__init__(min_len=1)
        self._allow_none = allow_none

    def __call__(self, value):
        if self._allow_none:
            return EnsureStrOrNoneWithEmptyIsNone()(value)
        else:
            return super()(value)

    def long_description(self):
        return 'value must be the name of a dataset sibling' \
               f"{' or None' if self._allow_none else ''}"

    def short_description(self):
        return f'sibling name{" (optional)" if self._allow_none else ""}'

    def for_dataset(self, dataset: Dataset):
        """Return an `EnsureChoice` with the sibling names for this dataset"""
        if not dataset.is_installed():
            return self

        choices = (
            r['name']
            for r in dataset.siblings(
                action='query',
                return_type='generator',
                result_renderer='disabled',
                on_failure='ignore')
            if 'name' in r
            and r.get('status') == 'ok'
            and r.get('type') == 'sibling'
            and r['name'] != 'here'
        )
        if self._allow_none:
            return EnsureChoice(None, *choices)
        else:
            return EnsureChoice(*choices)


class EnsureConfigProcedureName(EnsureChoice):
    def __init__(self, allow_none=False):
        self._allow_none = allow_none
        # all dataset-independent procedures
        super().__init__(*self._get_procs_())

    def long_description(self):
        return 'value must be the name of a configuration dataset procedure'

    def short_description(self):
        return 'configuration procedure'

    def for_dataset(self, dataset: Dataset):
        if not dataset.is_installed():
            return self
        return EnsureChoice(*self._get_procs_(dataset))

    def _get_procs_(self, dataset: Dataset = None):
        from datalad.local.run_procedure import RunProcedure
        for r in RunProcedure.__call__(
                dataset=dataset,
                discover=True,
                return_type='generator',
                result_renderer='disabled',
                on_failure='ignore'):
            if r.get('status') != 'ok' or not r.get(
                    'procedure_name', '').startswith('cfg_'):
                continue
            # strip 'cfg_' prefix, even when reporting, we do not want it
            # because commands like `create()` put it back themselves
            yield r['procedure_name'][4:]
        if self._allow_none:
            yield None


class EnsureExistingDirectory(Constraint):
    def __init__(self, allow_none=False):
        self._allow_none = allow_none

    def __call__(self, value):
        if value is None and self._allow_none:
            return None

        if not Path(value).is_dir():
            raise ValueError(
                f"{value} is not an existing directory")
        return value

    def short_description(self):
        return f'existing directory{" (optional)" if self._allow_none else ""}'
