# -*- mode: python ; coding: utf-8 -*-

import faster_whisper
import os

_EXCLUIR_MODULOS = [
    'torch', 'torchaudio', 'torchvision',
    'tensorflow', 'tensorboard', 'keras',
    'jax', 'jaxlib',
    'sklearn', 'matplotlib', 'pandas',
    'IPython', 'notebook', 'jupyter', 'jupyterlab',
    'sympy',
]

faster_whisper_path = os.path.dirname(faster_whisper.__file__)

# DLLs CUDA/ROCm/TensorRT — no se usan en distribución CPU
_CUDA_PATTERNS = (
    'cublas', 'cufft', 'curand', 'cusolver', 'cusparse',
    'cudnn', 'cuvid', 'nvcuda', 'nvjpeg', 'nvrtc',
    'onnxruntime_providers_cuda',
    'onnxruntime_providers_tensorrt',
    'onnxruntime_providers_rocm',
    '_rocm_sdk',
)

a = Analysis(
    ['speakme.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('assets', 'assets'),
        ('locales', 'locales'),
        ('modos.json', '.'),
        ('vocabulario.json', '.'),
        (os.path.join(faster_whisper_path, 'assets'), 'faster_whisper/assets'),
    ],
    hiddenimports=['onnx_asr', 'onnxruntime', 'pyautogui'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=_EXCLUIR_MODULOS,
    noarchive=False,
    optimize=0,
)

# Eliminar DLLs GPU que no se usan (~1.1 GB)
a.binaries = [b for b in a.binaries
              if not any(p in b[0].lower() for p in _CUDA_PATTERNS)]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='SpeakMe',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/SpeakMe.ico',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='SpeakMe',
)
