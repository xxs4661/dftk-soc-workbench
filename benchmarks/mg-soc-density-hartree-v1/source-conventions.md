# Saved density and Fourier conventions

These are interpretations of the official **QE `qe-7.5` tag**, checked before
reading the real G40 density. The preserved executable/JLL hashes establish the
observed binary identity; they do not prove that the binary was built from the
exact tagged source without patches. Historical source receipts and the actual
file headers remain separate evidence. No QE numerical source is copied here.

For the ordinary converged SCF branch used by G40, the density passed to the final
Hartree calculation is the orbital **output density**, without mixing. The
input and output arrays remain distinct when convergence is reached;
`v_of_rho` evaluates the latter before the exit saves it. This is not a claim
that the preceding eigensolve used that same output density.
[Density roles and convergence branch](https://github.com/QEF/q-e/blob/qe-7.5/PW/src/electrons.f90#L883-L1005),
[SCF exit save](https://github.com/QEF/q-e/blob/qe-7.5/PW/src/electrons.f90#L1207-L1256).

After `electrons` returns, the normal final write emits the XML and charge file
from the current state. The XML Hartree term is the global `ehart` divided by
`e2=2`; `v_of_rho` obtained it from total valence `rho%of_g(:,1)`. Thus a bound,
converged G40 SCF charge file and its final XML support a same-density Hartree
check. This chain does not justify applying the same state claim to arbitrary
nonconverged or bands outputs.
[Final execution/write order](https://github.com/QEF/q-e/blob/qe-7.5/PW/src/run_pwscf.f90#L176-L353),
[XML and density writes](https://github.com/QEF/q-e/blob/qe-7.5/PW/src/punch.f90#L74-L95),
[Hartree input](https://github.com/QEF/q-e/blob/qe-7.5/PW/src/v_of_rho.f90#L69-L83),
[XML units](https://github.com/QEF/q-e/blob/qe-7.5/PW/src/pw_restart_new.f90#L719-L727),
[Rydberg constant](https://github.com/QEF/q-e/blob/qe-7.5/Modules/constants.f90#L105).

For noncollinear charge-only calculations (`domag=false`), `write_scf` writes one
total-charge component. It passes the reciprocal columns **`bg*tpiba`**, already
in inverse bohr, and the native `rho%of_g`. The non-HDF5 records contain the
logical/count header, nine Float64 reciprocal components, the Fortran
`mill(3,ngm)` integer array, then one ComplexF64 record per saved component.
The parser independently tries both byte orders and 4/8-byte markers, integers
and logicals; only one fully valid candidate is accepted. Gamma-only and
multiple-component inputs are explicitly unsupported. Record markers and the
compiler's logical representation are format observations, not inferred from
agreement with DFTK.
[Charge-only write and reciprocal columns](https://github.com/QEF/q-e/blob/qe-7.5/PW/src/io_rho_xml.f90#L23-L62),
[Record layout and common Miller/coefficient order](https://github.com/QEF/q-e/blob/qe-7.5/Modules/io_base.f90#L402-L594).

QE's density forward transform uses the negative exponential and normalizes by
the number of grid points. The inverse is unnormalized. Accordingly the saved
coefficient is `nbar_m = FFT(n)_m/Ngrid`, in electron/bohr³; neither spin nor k
weights nor energy-unit factors are applied during extraction.
[Density transform](https://github.com/QEF/q-e/blob/qe-7.5/Modules/fft_rho.f90#L34-L93),
[Forward dispatch](https://github.com/QEF/q-e/blob/qe-7.5/FFTXlib/src/fft_fwinv.f90#L117-L216),
[FFTW3 normalization](https://github.com/QEF/q-e/blob/qe-7.5/FFTXlib/src/fft_scalar.FFTW3.f90#L432-L439),
[Forward sign](https://github.com/QEF/q-e/blob/qe-7.5/FFTXlib/src/fft_scalar.FFTW3.f90#L472-L475),
[FFTW definition](https://www.fftw.org/doc/The-1d-Discrete-Fourier-Transform-_0028DFT_0029.html).

The periodic Hartree routine checks charge as `Omega*real(rho_g(0))`, excludes
G=0 and uses `e2*4*pi/tpiba²` with dimensionless `gg`. The full-G branch includes
the energy factor `Omega/2`; its internal result is Ry. With the file's
`q=B*m`, conversion to Ha gives
`EH = 2*pi*Omega*sum_{m!=0} abs(nbar_m)^2/abs(q_m)^2`.
The independent diagnostic potential is
`vH_m = 4*pi*nbar_m/abs(q_m)^2`, with `vH_0=0`; it is not a native potential
array extraction. No extra gamma factor, background, local ionic term or
PspCorrection is included.
[Hartree charge, full-G and unit factors](https://github.com/QEF/q-e/blob/qe-7.5/PW/src/v_of_rho.f90#L664-L739).
