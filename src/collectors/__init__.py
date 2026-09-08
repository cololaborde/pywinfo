"""Coleccionistas de datos de hardware. Un archivo por categoría.

Cada módulo expone una función `parse_*` (o `get_*`) que recibe los
bloques parseados de hwinfo y/o el resumen `--short`, y devuelve la
estructura de datos correspondiente.
"""