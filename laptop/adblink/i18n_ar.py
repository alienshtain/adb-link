"""Arabic texts (Modern Standard Arabic). The three parts were written per source file."""
from .i18n_ar_a import AR as _A, PATTERNS as _PA
from .i18n_ar_b import AR as _B, PATTERNS as _PB
from .i18n_ar_c import AR as _C, PATTERNS as _PC
from .i18n_ar_extra import AR as _E, PATTERNS as _PE

AR = {**_A, **_B, **_C, **_E}
PATTERNS = [*_PE, *_PA, *_PB, *_PC]
