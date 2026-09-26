#ifndef LASERPAT_CONFIG_H
#define LASERPAT_CONFIG_H

// Auto-generated from configs/default.yaml

// PID Gains
#define PID_KP 0.5f
#define PID_KI 0.05f
#define PID_KD 0.1f

// Kalman Filter Matrices
#define KF_DT 0.03333333333333333f
#define KF_Q_NOISE 1.0f
#define KF_R_NOISE 5.0f

#endif // LASERPAT_CONFIG_H
