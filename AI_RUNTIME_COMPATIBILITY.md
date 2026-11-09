# Optional AI runtime compatibility

The main Thumb Finder application may run on newer Python versions, including Python 3.14.
The optional LaMa and Real-ESRGAN engines use a separate Python 3.11 environment because
some legacy AI dependencies do not publish compatible packages for Python 3.14.

On Windows, first use automatically downloads the official Python 3.11.9 per-user installer
and installs it privately under `%LOCALAPPDATA%/ThumbFinder/AI-Python311`. This does not
replace or modify the Python installation used by the main app. LaMa and enhancement each
have their own virtual environment and pinned dependency stack. The model files remain in
the ThumbFinder model cache and are reused between launches.

LaMa uses PyTorch 2.5.1 / torchvision 0.20.1 and explicitly installs the compatible Fire
0.5.0 dependency without forcing all packages to be binary wheels. Real-ESRGAN pins
basicsr 1.4.2 and realesrgan 0.3.0, avoiding the conflicting version ranges reported by pip.
