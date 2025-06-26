import inspireface as isf

# This step will automatically download the model on first use
# isf.reload("Gundam_RK3588")

# Configure a face quality detection function
opt = isf.HF_ENABLE_QUALITY
session = isf.InspireFaceSession(opt, isf.HF_DETECT_MODE_ALWAYS_DETECT)

