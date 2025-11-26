#!/usr/bin/env python3
"""
Script to modify LIQD app logo - change 'app' text to baby blue
"""
from PIL import Image
import numpy as np

def analyze_and_modify_logo(input_path, output_path):
    # Load the image
    img = Image.open(input_path)
    img_rgba = img.convert('RGBA')
    data = np.array(img_rgba)

    print(f"Image size: {img.size}")
    print(f"Image mode: {img.mode}")

    # Sample some pixels from the "D" area to get the exact baby blue color
    # The D is in the upper right portion of the image
    height, width = data.shape[:2]

    # Sample from right side where "D" should be (baby blue)
    baby_blue_samples = []
    for y in range(int(height * 0.2), int(height * 0.5)):
        for x in range(int(width * 0.7), int(width * 0.95)):
            r, g, b, a = data[y, x]
            # Look for blue-ish pixels (more blue than red/green)
            if b > 150 and b > r and b > g and a > 200:
                baby_blue_samples.append((r, g, b, a))

    if baby_blue_samples:
        # Calculate average baby blue color
        avg_r = int(np.mean([s[0] for s in baby_blue_samples]))
        avg_g = int(np.mean([s[1] for s in baby_blue_samples]))
        avg_b = int(np.mean([s[2] for s in baby_blue_samples]))
        baby_blue = (avg_r, avg_g, avg_b)
        print(f"Baby blue color detected: RGB{baby_blue} (#{avg_r:02x}{avg_g:02x}{avg_b:02x})")
    else:
        # Fallback to a standard baby blue
        baby_blue = (135, 206, 235)  # Sky blue
        print(f"Using fallback baby blue: RGB{baby_blue}")

    # Find and replace gray pixels in the "app" text area (lower portion)
    # The "app" text is in the bottom half of the image
    for y in range(int(height * 0.5), height):
        for x in range(width):
            r, g, b, a = data[y, x]

            # Detect gray pixels (where R, G, B are similar and not too dark/light)
            if a > 200:  # Only modify visible pixels
                # Check if pixel is grayish (R, G, B values are close)
                if abs(r - g) < 30 and abs(g - b) < 30 and abs(r - b) < 30:
                    # Check if it's in the gray range (not too dark, not too light)
                    if 150 < r < 220 and 150 < g < 220 and 150 < b < 220:
                        # Replace with baby blue
                        data[y, x] = [baby_blue[0], baby_blue[1], baby_blue[2], a]

    # Create new image from modified data
    result_img = Image.fromarray(data, 'RGBA')
    result_img.save(output_path)
    print(f"Modified logo saved to: {output_path}")

    return output_path

if __name__ == "__main__":
    input_file = "/tmp/original_logo.png"
    output_file = "LIQDapp_branding/logo_baby_blue.png"

    analyze_and_modify_logo(input_file, output_file)
