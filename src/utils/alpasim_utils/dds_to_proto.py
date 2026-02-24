"""DDS dataclass → protobuf conversion functions.

Used by the runtime services to convert DDS types back into protobuf LogEntry
messages for broadcasting (logging / evaluation).
"""

from __future__ import annotations

from alpasim_dds.types import common as dds_common
from alpasim_dds.types import controller as dds_controller
from alpasim_dds.types import egodriver as dds_ego
from alpasim_dds.types import physics as dds_physics
from alpasim_grpc.v0 import common_pb2 as proto_common
from alpasim_grpc.v0 import controller_pb2 as proto_controller
from alpasim_grpc.v0 import egodriver_pb2 as proto_ego
from alpasim_grpc.v0 import physics_pb2 as proto_physics

# ---------------------------------------------------------------------------
# Layer 1: common types
# ---------------------------------------------------------------------------


def vec3_to_proto(v: dds_common.Vec3) -> proto_common.Vec3:
    return proto_common.Vec3(x=v.x, y=v.y, z=v.z)


def quat_to_proto(q: dds_common.Quat) -> proto_common.Quat:
    return proto_common.Quat(w=q.w, x=q.x, y=q.y, z=q.z)


def pose_to_proto(p: dds_common.Pose) -> proto_common.Pose:
    return proto_common.Pose(
        vec=vec3_to_proto(p.vec),
        quat=quat_to_proto(p.quat),
    )


def dynamic_state_to_proto(ds: dds_common.DynamicState) -> proto_common.DynamicState:
    return proto_common.DynamicState(
        angular_velocity=vec3_to_proto(ds.angular_velocity) if ds.angular_velocity else None,
        linear_velocity=vec3_to_proto(ds.linear_velocity) if ds.linear_velocity else None,
        linear_acceleration=vec3_to_proto(ds.linear_acceleration) if ds.linear_acceleration else None,
        angular_acceleration=vec3_to_proto(ds.angular_acceleration) if ds.angular_acceleration else None,
    )


def pose_at_time_to_proto(pat: dds_common.PoseAtTime) -> proto_common.PoseAtTime:
    return proto_common.PoseAtTime(
        pose=pose_to_proto(pat.pose),
        timestamp_us=pat.timestamp_us,
    )


def state_at_time_to_proto(sat: dds_common.StateAtTime) -> proto_common.StateAtTime:
    return proto_common.StateAtTime(
        timestamp_us=sat.timestamp_us,
        pose=pose_to_proto(sat.pose),
        state=dynamic_state_to_proto(sat.state) if sat.state else None,
    )


def trajectory_to_proto(t: dds_common.Trajectory) -> proto_common.Trajectory:
    return proto_common.Trajectory(
        poses=[pose_at_time_to_proto(p) for p in (t.poses or [])],
    )


def aabb_to_proto(a: dds_common.AABB) -> proto_common.AABB:
    return proto_common.AABB(size_x=a.size_x, size_y=a.size_y, size_z=a.size_z)


def version_response_to_proto(v: dds_common.VersionResponse) -> proto_common.VersionId:
    proto = proto_common.VersionId(
        version_id=v.version_id,
        git_hash=v.git_hash,
    )
    if v.api_version:
        proto.grpc_api_version.CopyFrom(
            proto_common.VersionId.APIVersion(
                major=v.api_version.major,
                minor=v.api_version.minor,
                patch=v.api_version.patch,
            )
        )
    return proto


# ---------------------------------------------------------------------------
# Layer 2: egodriver types
# ---------------------------------------------------------------------------


def drive_request_to_proto(req: dds_ego.DriveRequest) -> proto_ego.DriveRequest:
    return proto_ego.DriveRequest(
        session_uuid=req.session_uuid,
        time_now_us=req.time_now_us,
        time_query_us=req.time_query_us,
        renderer_data=bytes(req.renderer_data or []),
    )


def drive_response_to_proto(resp: dds_ego.DriveResponse) -> proto_ego.DriveResponse:
    proto = proto_ego.DriveResponse()
    if resp.trajectory:
        proto.trajectory.CopyFrom(trajectory_to_proto(resp.trajectory))
    if resp.debug_info:
        di = proto_ego.DriveResponse.DebugInfo(
            unstructured_debug_info=bytes(resp.debug_info.unstructured_debug_info or []),
        )
        if resp.debug_info.sampled_trajectories:
            for st in resp.debug_info.sampled_trajectories:
                di.sampled_trajectories.append(trajectory_to_proto(st))
        proto.debug_info.CopyFrom(di)
    return proto


def drive_session_request_to_proto(
    req: dds_ego.DriveSessionRequest,
) -> proto_ego.DriveSessionRequest:
    """Convert DriveSessionRequest. CameraSpec conversion is skipped."""
    proto = proto_ego.DriveSessionRequest(
        session_uuid=req.session_uuid,
        random_seed=req.random_seed,
    )
    if req.debug_info and req.debug_info.scene_id:
        proto.debug_info.CopyFrom(
            proto_ego.DriveSessionRequest.DebugInfo(scene_id=req.debug_info.scene_id)
        )
    return proto


def rollout_camera_image_to_proto(
    img: dds_ego.RolloutCameraImage,
) -> proto_ego.RolloutCameraImage:
    return proto_ego.RolloutCameraImage(
        session_uuid=img.session_uuid,
        camera_image=proto_ego.RolloutCameraImage.CameraImage(
            frame_start_us=img.camera_image.frame_start_us,
            frame_end_us=img.camera_image.frame_end_us,
            image_bytes=bytes(img.camera_image.image_bytes or []),
            logical_id=img.camera_image.logical_id,
        ),
    )


def rollout_ego_trajectory_to_proto(
    ego: dds_ego.RolloutEgoTrajectory,
) -> proto_ego.RolloutEgoTrajectory:
    proto = proto_ego.RolloutEgoTrajectory(session_uuid=ego.session_uuid)
    if ego.trajectory:
        proto.trajectory.CopyFrom(trajectory_to_proto(ego.trajectory))
    if ego.dynamic_state:
        proto.dynamic_state.CopyFrom(dynamic_state_to_proto(ego.dynamic_state))
    return proto


def route_request_to_proto(req: dds_ego.RouteRequest) -> proto_ego.RouteRequest:
    proto = proto_ego.RouteRequest(session_uuid=req.session_uuid)
    if req.route:
        route = proto_ego.Route(timestamp_us=req.route.timestamp_us)
        for wp in req.route.waypoints or []:
            route.waypoints.append(vec3_to_proto(wp))
        proto.route.CopyFrom(route)
    return proto


def ground_truth_request_to_proto(
    req: dds_ego.GroundTruthRequest,
) -> proto_ego.GroundTruthRequest:
    proto = proto_ego.GroundTruthRequest(session_uuid=req.session_uuid)
    if req.ground_truth:
        gt = proto_ego.GroundTruth(timestamp_us=req.ground_truth.timestamp_us)
        if req.ground_truth.trajectory:
            gt.trajectory.CopyFrom(trajectory_to_proto(req.ground_truth.trajectory))
        proto.ground_truth.CopyFrom(gt)
    return proto


# ---------------------------------------------------------------------------
# Layer 3: controller types
# ---------------------------------------------------------------------------


def run_controller_request_to_proto(
    req: dds_controller.RunControllerAndVehicleModelRequest,
) -> proto_controller.RunControllerAndVehicleModelRequest:
    proto = proto_controller.RunControllerAndVehicleModelRequest(
        session_uuid=req.session_uuid,
        future_time_us=req.future_time_us,
        coerce_dynamic_state=req.coerce_dynamic_state,
    )
    if req.state:
        proto.state.CopyFrom(state_at_time_to_proto(req.state))
    if req.planned_trajectory_in_rig:
        proto.planned_trajectory_in_rig.CopyFrom(
            trajectory_to_proto(req.planned_trajectory_in_rig)
        )
    return proto


def run_controller_response_to_proto(
    resp: dds_controller.RunControllerAndVehicleModelResponse,
) -> proto_controller.RunControllerAndVehicleModelResponse:
    proto = proto_controller.RunControllerAndVehicleModelResponse()
    if resp.pose_local_to_rig:
        proto.pose_local_to_rig.CopyFrom(pose_at_time_to_proto(resp.pose_local_to_rig))
    if resp.pose_local_to_rig_estimated:
        proto.pose_local_to_rig_estimated.CopyFrom(
            pose_at_time_to_proto(resp.pose_local_to_rig_estimated)
        )
    if resp.dynamic_state:
        proto.dynamic_state.CopyFrom(dynamic_state_to_proto(resp.dynamic_state))
    if resp.dynamic_state_estimated:
        proto.dynamic_state_estimated.CopyFrom(
            dynamic_state_to_proto(resp.dynamic_state_estimated)
        )
    return proto


# ---------------------------------------------------------------------------
# Layer 4: physics types
# ---------------------------------------------------------------------------

_DDS_STATUS_TO_PROTO = {
    dds_physics.GroundIntersectionStatus.SUCCESSFUL_UPDATE: proto_physics.PhysicsGroundIntersectionReturn.SUCCESSFUL_UPDATE,
    dds_physics.GroundIntersectionStatus.INSUFFICIENT_POINTS_FITPLANE: proto_physics.PhysicsGroundIntersectionReturn.INSUFFICIENT_POINTS_FITPLANE,
    dds_physics.GroundIntersectionStatus.HIGH_TRANSLATION: proto_physics.PhysicsGroundIntersectionReturn.HIGH_TRANSLATION,
    dds_physics.GroundIntersectionStatus.HIGH_ROTATION: proto_physics.PhysicsGroundIntersectionReturn.HIGH_ROTATION,
}


def _pose_pair_to_proto(
    pp: dds_physics.PosePair,
) -> proto_physics.PhysicsGroundIntersectionRequest.PosePair:
    return proto_physics.PhysicsGroundIntersectionRequest.PosePair(
        now_pose=pose_to_proto(pp.now_pose),
        future_pose=pose_to_proto(pp.future_pose),
    )


def _ego_data_to_proto(
    ed: dds_physics.EgoData,
) -> proto_physics.PhysicsGroundIntersectionRequest.EgoData:
    return proto_physics.PhysicsGroundIntersectionRequest.EgoData(
        aabb=aabb_to_proto(ed.aabb),
        pose_pair=_pose_pair_to_proto(ed.pose_pair),
    )


def _other_object_to_proto(
    oo: dds_physics.OtherObject,
) -> proto_physics.PhysicsGroundIntersectionRequest.OtherObject:
    return proto_physics.PhysicsGroundIntersectionRequest.OtherObject(
        aabb=aabb_to_proto(oo.aabb),
        pose_pair=_pose_pair_to_proto(oo.pose_pair),
    )


def _return_pose_to_proto(
    rp: dds_physics.ReturnPose,
) -> proto_physics.PhysicsGroundIntersectionReturn.ReturnPose:
    return proto_physics.PhysicsGroundIntersectionReturn.ReturnPose(
        pose=pose_to_proto(rp.pose),
        status=_DDS_STATUS_TO_PROTO.get(
            rp.status,
            proto_physics.PhysicsGroundIntersectionReturn.SUCCESSFUL_UPDATE,
        ),
    )


def physics_request_to_proto(
    req: dds_physics.PhysicsGroundIntersectionRequest,
) -> proto_physics.PhysicsGroundIntersectionRequest:
    proto = proto_physics.PhysicsGroundIntersectionRequest(
        scene_id=req.scene_id,
        now_us=req.now_us,
        future_us=req.future_us,
    )
    if req.ego_data:
        proto.ego_data.CopyFrom(_ego_data_to_proto(req.ego_data))
    if req.other_objects:
        for oo in req.other_objects:
            proto.other_objects.append(_other_object_to_proto(oo))
    return proto


def physics_response_to_proto(
    resp: dds_physics.PhysicsGroundIntersectionReturn,
) -> proto_physics.PhysicsGroundIntersectionReturn:
    proto = proto_physics.PhysicsGroundIntersectionReturn()
    if resp.ego_pose:
        proto.ego_pose.CopyFrom(_return_pose_to_proto(resp.ego_pose))
    if resp.other_poses:
        for rp in resp.other_poses:
            proto.other_poses.append(_return_pose_to_proto(rp))
    return proto
