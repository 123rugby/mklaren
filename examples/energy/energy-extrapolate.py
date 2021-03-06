hlp = """
    Test prediction with low-rank approximations on the energy dataset with matern, exponential and
    periodic kernels. Tested methods are Mklaren, ICD, CSI, Nystrom, FITC, RFF_KMP.

"""

if __name__ == "__main__":
    import matplotlib
    matplotlib.use("Agg")

import argparse
import csv
import os
import numpy as np
import itertools as it
from mklaren.kernel.kernel import kernel_sum, periodic_kernel, linear_kernel_noise
from mklaren.kernel.kinterface import Kinterface
from sklearn.metrics import mean_squared_error as mse
from datasets.energy import load_energy
from examples.inducing_points.inducing_points import plot_signal_subplots, test
from scipy.stats import pearsonr

# Hyperparameters
delta = 70                                          # Look-ahead parameter
rank_range = (7, )                                  # Tested rank range
linear_bias = 1                                     # Bias for linear kernel
linear_noise = 1                                    # Noise term
lambda_range = [0] + list(np.logspace(-5, -1, 5))   # L2-regularization parameter range


def process(dataset, outdir):
    """
    Run experiments with epcified parameters.
    :param dataset: Dataset key.
    :param outdir: Output directory.
    :return:
    """

    # Methods that support periodicity
    kernel_function = periodic_kernel
    pars = {"l": np.logspace(-3, 3, 13),
            "per": np.logspace(-3, 3, 13)}
    methods = ("Mklaren", "Arima", "ICD", "CSI", "Nystrom", )

    # Data parameters
    signals = ["T%d" % i for i in range(1, 10)]
    assert dataset in signals
    inxs = range(1, 19)

    # Store results
    if not os.path.exists(outdir): os.makedirs(outdir)
    fname = os.path.join(outdir, "%s.csv" % dataset)
    subdname = os.path.join(outdir, "_%s" % dataset)
    if not os.path.exists(subdname):
        os.makedirs(subdname)

    header = ["experiment", "signal",  "tsi", "method",
              "mse_f", "mse_y", "corr_y", "mse_val", "rank", "lbd", "n", "time"]
    writer = csv.DictWriter(open(fname, "w", buffering=0), fieldnames=header)
    writer.writeheader()

    # Load energy consumption data
    data = load_energy(signal=dataset)
    data_out = load_energy(signal="T_out")
    X, labels = data["data"], data["labels"]
    X_out, _ = data_out["data"], data_out["labels"]

    # Normalize by outside temperature
    # Assume true signal is the mean of the signals
    Y = X - X_out
    N, n = Y.shape

    # Training, validation, test
    x = np.atleast_2d(np.arange(0, n)).T
    xt = np.atleast_2d(np.arange(0, int(n/2))).T
    xv = np.atleast_2d(np.arange(int(n/2), int(3 * n / 4))).T
    xp = np.atleast_2d(np.arange(int(3*n/4), n)).T

    Nt, Np = xt.shape[0], xp.shape[0]
    Nv = xv.shape[0]
    f = Y[1:19, xt].mean(axis=0).ravel()
    
    for rank, lbd, tsi in it.product(rank_range, lambda_range, inxs):
        y = Y[tsi, :].reshape((n, 1))
        yt = Y[tsi, xt].reshape((Nt, 1))
        yv = Y[tsi, xv].reshape((Nv, 1))
        yp = Y[tsi, xp].reshape((Np, 1))

        # Sum and List of kernels
        vals = list(it.product(*pars.values()))
        names = pars.keys()
        Klist = [Kinterface(data=xt, kernel=kernel_function, row_normalize=False,
                            kernel_args=dict([(nam, v) for nam, v in zip(names, vlist)])) for vlist in vals]
        Klist += [Kinterface(data=xt, kernel=linear_kernel_noise,
                             kernel_args={"b": linear_bias, "noise": linear_noise}, row_normalize=False)]

        kernels = [linear_kernel_noise] + [kernel_function] * len(vals)
        kargs = [{"b": linear_bias, "noise": 1e-3}] \
                + [dict([(nam, v) for nam, v in zip(names, vlist)]) for vlist in vals]
        Ksum = Kinterface(data=xt, kernel=kernel_sum, row_normalize=False,
                          kernel_args={"kernels": kernels,
                                       "kernels_args": kargs})

        # Fit models and plot signal
        # Remove True anchors, as they are non-existent
        try:
            models = test(Ksum=Ksum, Klist=Klist,
                          inxs=range(rank),
                          X=xt, Xp=xp, y=yt, f=f, delta=delta, lbd=lbd,
                          methods=methods)
            models_val = test(Ksum=Ksum, Klist=Klist,
                              inxs=range(rank),
                              X=xt, Xp=xv, y=yt, f=f, delta=delta, lbd=lbd,
                              methods=methods)
            del models["True"]
            del models_val["True"]

            # Store file as pdf + eps
            fname = os.path.join(subdname, "plot_multi-%s_tsi-%d_lbd-%.6f_rank-%d.pdf" % (dataset, tsi, lbd, rank))
            plot_signal_subplots(X=x, Xp=xp, y=y, f=None, models=models, f_out=fname)

            fname = os.path.join(subdname, "plot_multi-%s_tsi-%d_lbd-%.6f_rank-%d.eps" % (dataset, tsi, lbd, rank))
            plot_signal_subplots(X=x, Xp=xp, y=y, f=None, models=models, f_out=fname)

            for ky in models.keys():
                mse_yp = mse(models[ky]["yp"].ravel(), yp.ravel())
                mse_val = mse(models_val[ky]["yp"].ravel(), yv.ravel())
                corr_yp = pearsonr(models[ky]["yp"].ravel(), yp.ravel())[0]

                time = models[ky]["time"]
                row = {"experiment": "cosine",
                       "signal": dataset, "tsi": tsi, "method": ky,
                       "mse_f": 0, "mse_y": mse_yp, "corr_y": corr_yp, "mse_val": mse_val,
                       "rank": rank, "lbd": lbd, "n": n, "time": time}
                writer.writerow(row)
        except Exception as e:
            print("Exception: %s %s" % (str(e), e.message))
            continue


if __name__ == "__main__":
    # Input arguments
    parser = argparse.ArgumentParser(description=hlp)
    parser.add_argument("dataset", help="Time series. One of {T1-T9}.")
    parser.add_argument("output",  help="Output directory.")
    args = parser.parse_args()

    # Output directory
    process(args.dataset, args.output)
