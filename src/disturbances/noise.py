import numpy as np

def add_gaussian_noise(image: np.ndarray, sigma: float, rng: np.random.Generator = None) -> np.ndarray:
    if sigma <= 0:
        return image
    if rng is None:
        rng = np.random.default_rng()
    noise = rng.normal(0, sigma, image.shape)
    noisy_img = image.astype(np.float32) + noise
    return np.clip(noisy_img, 0, 255).astype(np.uint8)

def add_poisson_noise(image: np.ndarray, rng: np.random.Generator = None) -> np.ndarray:
    # Scale image to avoid extreme values and apply Poisson
    # Poisson noise is signal-dependent
    img_scaled = image.astype(np.float32) / 255.0
    # Lambda for poisson is the scaled pixel value * max_photons (approx)
    # Using a typical factor for shot noise
    if rng is None:
        rng = np.random.default_rng()
    noisy_img = rng.poisson(img_scaled * 100.0) / 100.0 * 255.0
    return np.clip(noisy_img, 0, 255).astype(np.uint8)

def add_salt_and_pepper_noise(image: np.ndarray, percent: float, rng: np.random.Generator = None) -> np.ndarray:
    if percent <= 0:
        return image
    if rng is None:
        rng = np.random.default_rng()
    noisy_img = np.copy(image)
    num_pixels = image.size
    num_noise = int(np.ceil(num_pixels * (percent / 100.0)))
    
    # Add Salt (255)
    coords_salt = [rng.integers(0, i, num_noise // 2) for i in image.shape]
    noisy_img[tuple(coords_salt)] = 255
    
    # Add Pepper (0)
    coords_pepper = [rng.integers(0, i, num_noise // 2) for i in image.shape]
    noisy_img[tuple(coords_pepper)] = 0
    
    return noisy_img

def apply_sensor_noise(image: np.ndarray, gaussian_sigma: float, poisson: bool, sp_percent: float, rng: np.random.Generator = None) -> np.ndarray:
    """
    Applies the configured combination of noise to the image.
    """
    img = np.copy(image)
    if poisson:
        img = add_poisson_noise(img, rng)
    if gaussian_sigma > 0:
        img = add_gaussian_noise(img, gaussian_sigma, rng)
    if sp_percent > 0:
        img = add_salt_and_pepper_noise(img, sp_percent, rng)
    return img
