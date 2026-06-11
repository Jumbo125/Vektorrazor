# Third-party notices for optional Real-ESRGAN support

Vektorrazor can optionally use Real-ESRGAN ncnn Vulkan for local AI-based image upscaling.

This file is intended to be shipped together with Vektorrazor release packages when Real-ESRGAN executables or model files are included.

## Included / referenced third-party components

### Real-ESRGAN

- Project: Real-ESRGAN
- Author / copyright holder: Xintao Wang
- License: BSD 3-Clause License
- Repository: https://github.com/xinntao/Real-ESRGAN

Required action when redistributing: keep the BSD 3-Clause license text and copyright notice in the release package.

### Real-ESRGAN ncnn Vulkan

- Project: Real-ESRGAN ncnn Vulkan
- Author / copyright holder: Xintao Wang
- License: MIT License
- Repository: https://github.com/xinntao/Real-ESRGAN-ncnn-vulkan

Required action when redistributing: keep the MIT license text and copyright notice in the release package.

### realsr-ncnn-vulkan

Real-ESRGAN ncnn Vulkan states that it heavily borrows from realsr-ncnn-vulkan.

- Project: realsr-ncnn-vulkan
- Author / copyright holder: nihui
- License: MIT License

Required action when redistributing: keep the MIT license text and copyright notice included in the Real-ESRGAN ncnn Vulkan license.

## No endorsement

Vektorrazor is not officially affiliated with, endorsed by, or supported by Real-ESRGAN, Xintao Wang, Tencent ARC Lab or nihui.

## Practical release checklist

When shipping Real-ESRGAN with Vektorrazor, include at least:

```text
vektorrazor_config/real_esrgan/THIRD_PARTY_NOTICES.md
vektorrazor_config/real_esrgan/LICENSE-Real-ESRGAN-BSD-3-Clause.txt
vektorrazor_config/real_esrgan/LICENSE-Real-ESRGAN-ncnn-vulkan-MIT.txt
```

Do not remove copyright notices from downloaded third-party files.
