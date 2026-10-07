// Copyright 2026 Overte contributors
// SPDX-License-Identifier: Apache-2.0 AND MIT
// Native curve formulas: libraries/render-utils/src/toneMapping.slf.
// The filmic curve derives from these MIT-licensed sources:
// https://github.com/TheRealMJP/BakingLab/blob/master/BakingLab/ACES.hlsl
// Copyright (c) 2022 @64
// https://github.com/64/64.github.io/blob/src/code/tonemapping/tonemap.cpp
// Copyright (c) 2016 MJP
//
// Permission is hereby granted, free of charge, to any person obtaining a copy
// of this software and associated documentation files (the "Software"), to deal
// in the Software without restriction, including without limitation the rights
// to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
// copies of the Software, and to permit persons to whom the Software is
// furnished to do so, subject to the following conditions:
//
// The above copyright notice and this permission notice shall be included in all
// copies or substantial portions of the Software.
//
// THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
// IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
// FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
// AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
// LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
// OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
// SOFTWARE.

export const nativeToneOutputFragment = /* glsl */ `
uniform sampler2D worldTexture;
uniform float twoPowExposure;
uniform int toneCurve;
varying vec2 worldUV;
vec3 nativeCurve(vec3 color) {
  if (toneCurve == 3) {
    mat3 inputMatrix = mat3(0.59719,0.07600,0.02840, 0.35458,0.90834,0.13383, 0.04823,0.01566,0.83777);
    mat3 outputMatrix = mat3(1.60475,-0.10208,-0.00327, -0.53108,1.10813,-0.07276, -0.07367,-0.00605,1.07602);
    color = inputMatrix * color;
    vec3 a = color * (color + 0.0245786) - 0.000090537;
    vec3 b = color * (0.983729 * color + 0.4329510) + 0.238081;
    return clamp(outputMatrix * (a / b), vec3(0.0), vec3(1.0));
  }
  if (toneCurve == 2) {
    float oldLuminance = dot(color, vec3(0.2126,0.7152,0.722));
    // Avoid native 0/0 for exact black; the intended output is black.
    if (oldLuminance == 0.0) return vec3(0.0);
    float newLuminance = oldLuminance * (1.0 + oldLuminance / 4.0) / (1.0 + oldLuminance);
    return color * (newLuminance / oldLuminance);
  }
  if (toneCurve == 0) return pow(max(color, vec3(0.0)), vec3(2.2));
  return color;
}
vec3 nativeSRGB(vec3 color) {
  color = max(color, vec3(0.0));
  return mix(1.055 * pow(color, vec3(1.0 / 2.4)) - 0.055, 12.92 * color, lessThanEqual(color, vec3(0.0031308)));
}
void main() {
  vec3 color = nativeCurve(texture2D(worldTexture, worldUV).rgb * twoPowExposure);
  gl_FragColor = vec4(clamp(nativeSRGB(color), vec3(0.0), vec3(1.0)), 1.0);
}`;
