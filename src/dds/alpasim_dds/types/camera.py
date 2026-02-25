"""Camera-related types extracted from sensorsim.proto.

Sensorsim itself stays on gRPC, but DriveSessionRequest embeds camera
definitions so we need these as DDS-serialisable structs.
"""

from dataclasses import dataclass, field
from cyclonedds.idl import IdlEnum, IdlStruct
from cyclonedds.idl.types import float64, uint32, sequence

from alpasim_dds.types.common import Pose


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ShutterType(IdlEnum):
    UNKNOWN = 0
    ROLLING_TOP_TO_BOTTOM = 1
    ROLLING_LEFT_TO_RIGHT = 2
    ROLLING_BOTTOM_TO_TOP = 3
    ROLLING_RIGHT_TO_LEFT = 4
    GLOBAL = 5


# ---------------------------------------------------------------------------
# Camera model parameters
# ---------------------------------------------------------------------------


@dataclass
class LinearCde(IdlStruct):
    linear_c: float64 = 0.0
    linear_d: float64 = 0.0
    linear_e: float64 = 0.0


class FthetaPolynomialType(IdlEnum):
    UNKNOWN = 0
    PIXELDIST_TO_ANGLE = 1
    ANGLE_TO_PIXELDIST = 2


@dataclass
class FthetaCameraParam(IdlStruct):
    principal_point_x: float64 = 0.0
    principal_point_y: float64 = 0.0
    reference_poly: FthetaPolynomialType = FthetaPolynomialType.UNKNOWN
    pixeldist_to_angle_poly: sequence[float64] = ()
    angle_to_pixeldist_poly: sequence[float64] = ()
    max_angle: float64 = 0.0
    linear_cde: LinearCde = field(default_factory=LinearCde)


@dataclass
class OpenCVPinholeCameraParam(IdlStruct):
    principal_point_x: float64 = 0.0
    principal_point_y: float64 = 0.0
    focal_length_x: float64 = 0.0
    focal_length_y: float64 = 0.0
    radial_coeffs: sequence[float64] = ()
    tangential_coeffs: sequence[float64] = ()
    thin_prism_coeffs: sequence[float64] = ()


@dataclass
class OpenCVFisheyeCameraParam(IdlStruct):
    principal_point_x: float64 = 0.0
    principal_point_y: float64 = 0.0
    focal_length_x: float64 = 0.0
    focal_length_y: float64 = 0.0
    radial_coeffs: sequence[float64] = ()
    max_angle: float64 = 0.0


class BivariateReferencePolynomial(IdlEnum):
    FORWARD = 0
    BACKWARD = 1


@dataclass
class BivariateWindshieldModelParameters(IdlStruct):
    reference_poly: BivariateReferencePolynomial = BivariateReferencePolynomial.FORWARD
    horizontal_poly: sequence[float64] = ()
    vertical_poly: sequence[float64] = ()
    horizontal_poly_inverse: sequence[float64] = ()
    vertical_poly_inverse: sequence[float64] = ()


# ---------------------------------------------------------------------------
# CameraSpec  (proto uses oneof — DDS has no union, so we use default instances)
# ---------------------------------------------------------------------------


@dataclass
class CameraSpec(IdlStruct):
    # Exactly one of the three camera params should be set.
    # DDS has no oneof; all get default instances to avoid serialize failures.
    ftheta_param: FthetaCameraParam = field(default_factory=FthetaCameraParam)
    opencv_pinhole_param: OpenCVPinholeCameraParam = field(default_factory=OpenCVPinholeCameraParam)
    opencv_fisheye_param: OpenCVFisheyeCameraParam = field(default_factory=OpenCVFisheyeCameraParam)

    logical_id: str = ""
    resolution_h: uint32 = 0
    resolution_w: uint32 = 0
    shutter_type: ShutterType = ShutterType.UNKNOWN

    bivariate_windshield_model_param: BivariateWindshieldModelParameters = field(default_factory=BivariateWindshieldModelParameters)


# ---------------------------------------------------------------------------
# AvailableCamera (used in DriveSessionRequest)
# ---------------------------------------------------------------------------


@dataclass
class AvailableCamera(IdlStruct):
    intrinsics: CameraSpec = field(default_factory=CameraSpec)
    rig_to_camera: Pose = field(default_factory=Pose)
    logical_id: str = ""
