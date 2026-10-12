"""가정한 정확한 센서 입력에 실제 MyTrack·DPath·lead 동역학을 적용한다."""
from offline_io import prepare

prepare(solver_overlay=True)
from openpilot.cereal import car, log
from opendbc.car.radar_tracks import MyTrack
from openpilot.selfdrive.carrot.radar_motion import DPathRadarController


class DPathTruthBridge:
  def __init__(self, *, period_s=.06):
    self.period_s = period_s
    self.next_sample = None
    self.track = None
    self.points = []
    self.last_sample = None
    self.state = log.RadarState()
    self.controller = DPathRadarController(enable_radar_tracks=1, production_live_tracks=True)

  def update(self, *, now_s, v_ego, a_ego, model, truth):
    if self.next_sample is None:
      self.next_sample = now_s
    if now_s + 1e-9 >= self.next_sample:
      self.next_sample += self.period_s
      self.last_sample = now_s
      self.points = []
      if truth["present"]:
        point = car.RadarData.RadarPoint(trackId=1001, dRel=float(max(.01, truth["gap_m"])),
                                         yRel=float(truth["y_rel_m"]), vRel=float(truth["lead_speed_mps"]-v_ego),
                                         vLead=float(truth["lead_speed_mps"]), measured=True, radarSource="frontRadar",
                                         yvRel=0.0, aRel=float(truth["lead_accel_mps2"]-a_ego), trackState=0)
        if self.track is None:
          self.track = MyTrack(1001, point, self.period_s)
        self.track.update(point, a_ego)
        self.track.write_acceleration(point)
        self.points = [point]
      else:
        self.track = None
    if model.frameId != getattr(self, "last_model_frame", None):
      self.last_model_frame = model.frameId
      output = self.controller.update(time_s=now_s, v_ego=v_ego, radar_points=self.points, model=model,
                                      radar_to_model_time_s=0 if self.last_sample is None else now_s-self.last_sample)
      self.state = log.RadarState()
      if output.lead_one:
        self.state.leadOne = output.lead_one
      if output.lead_two:
        self.state.leadTwo = output.lead_two
    return self.state
