"""실제 native solver와 원형 planner/controller 클래스가 함께 로드되는지 검사한다."""
import json
from offline_io import MemoryParams, prepare

prepare(solver_overlay=True)
from openpilot.selfdrive.controls.lib.longitudinal_mpc_lib.long_mpc import LongitudinalMpc
mpc = LongitudinalMpc()
print("native solver:", type(mpc.solver), flush=True)
from openpilot.selfdrive.carrot.carrot_functions import CarrotPlanner
from openpilot.selfdrive.carrot.signal_assist import SignalAssist
from openpilot.selfdrive.carrot.signal_start_guard import SignalStartGuard
from openpilot.selfdrive.carrot.signal_stop_prepare import SignalStopPrepare
carrot = CarrotPlanner(signal_assist=SignalAssist(), start_guard=SignalStartGuard(), stop_prepare=SignalStopPrepare())
from opendbc.car import gen_empty_fingerprint
from opendbc.car.toyota.interface import CarInterface
from opendbc.car.toyota.values import CAR
CP = CarInterface.get_params(CAR.TOYOTA_RAV4_TSS2_2022, gen_empty_fingerprint(), [], True, False, False)
from openpilot.selfdrive.controls.lib.longitudinal_planner import LongitudinalPlanner
from openpilot.selfdrive.controls.lib.longcontrol import LongControl
planner = LongitudinalPlanner(CP)
long_control = LongControl(CP)
print(json.dumps({"real_objects": [type(value).__module__ + "." + type(value).__name__ for value in (carrot, planner, long_control)],
                  "carFingerprint": CP.carFingerprint, "brand": CP.brand, "local_cp_openpilotLongitudinalControl": CP.openpilotLongitudinalControl,
                  "solver_class": type(planner.mpc.solver).__module__ + "." + type(planner.mpc.solver).__name__,
                  "default_params": len(MemoryParams.values)}, indent=2), flush=True)
