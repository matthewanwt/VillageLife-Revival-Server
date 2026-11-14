"""Original single-precision timer pricing."""
from __future__ import annotations

import math
import struct


def f32(value):
    return struct.unpack('<f', struct.pack('<f', value))[0]


def gem_price(world, remaining, category=''):
    if remaining <= 0:
        return 0
    times = [f32(float(world.global_value(f'gemCurveVariable{category}Time{label}')))
             for label in ('1min', '1hour', '1day', '1week')]
    prices = [f32(float(world.global_value(f'gemCalc{category}Value{index}')))
              for index in range(1, 5)]
    time_left = min(f32(remaining), times[-1])
    index = 0 if time_left < times[1] else 1 if time_left < times[2] else 2
    scale = f32(f32(times[index + 1] - times[index]) / f32(prices[index + 1] - prices[index]))
    return max(1, math.floor(f32(prices[index] + f32(f32(time_left - times[index]) / scale))))

