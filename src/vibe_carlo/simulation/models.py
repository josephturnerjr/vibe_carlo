from pathlib import Path

import numpy as np
import numpy.typing as npt

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# Column indices in the loaded array
COL_SP500 = 0
COL_BOND = 1
COL_CPI = 2


def load_historical_data() -> npt.NDArray[np.float64]:
    """Load historical returns CSV into a NumPy array.

    Returns an (N, 3) array with columns: sp500_return, bond_return, cpi_inflation.
    """
    csv_path = DATA_DIR / "historical_returns.csv"
    data = np.loadtxt(csv_path, delimiter=",", skiprows=1, usecols=(1, 2, 3))
    return data.astype(np.float64)
