#include "tests/libsafety/safety.c"

// 실제 Panda 드라이버의 전송 보관 상태. 기본 libsafety fixture가 정의하지
// 않는 이 변수만 제공하며 안전 검사 함수는 모두 원본을 실행한다.
bool safety_tx_buffered_for_fwd = false;

// 오프라인 시험 패킷만 만들며 USB, 소켓 또는 차량에 연결하지 않는다.
static bool probe_make_packet(CANPacket_t *packet, uint32_t addr, uint8_t bus,
                              uint8_t len, const uint8_t *data) {
  if ((bus > 7U) || (len > CANPACKET_DATA_SIZE_MAX) || (addr > 0x1FFFFFFFU)) {
    return false;
  }
  bool found = false;
  uint8_t dlc = 0U;
  for (uint8_t i = 0U; i < sizeof(dlc_to_len); i++) {
    if (dlc_to_len[i] == len) {
      dlc = i;
      found = true;
      break;
    }
  }
  if (!found) return false;
  *packet = (CANPacket_t){0};
  packet->addr = addr;
  packet->extended = addr >= 0x800U;
  packet->bus = bus;
  packet->data_len_code = dlc;
  packet->fd = len > 8U;
  for (uint8_t i = 0U; i < len; i++) packet->data[i] = data[i];
  can_set_checksum(packet);
  return true;
}

int probe_tx(uint32_t addr, uint8_t bus, uint8_t len, const uint8_t *data) {
  CANPacket_t packet;
  if (!probe_make_packet(&packet, addr, bus, len, data)) return -1;
  return safety_tx_hook(&packet);
}

int probe_rx(uint32_t addr, uint8_t bus, uint8_t len, const uint8_t *data) {
  CANPacket_t packet;
  if (!probe_make_packet(&packet, addr, bus, len, data)) return -1;
  return safety_rx_hook(&packet);
}

int probe_fwd(uint32_t addr, uint8_t bus, uint8_t len, const uint8_t *data) {
  CANPacket_t packet;
  if (!probe_make_packet(&packet, addr, bus, len, data)) return -2;
  return safety_fwd_hook(&packet);
}

int probe_packet_size(void) { return sizeof(CANPacket_t); }

int probe_helper_accel(int desired_accel, int minimum, int maximum) {
  const LongitudinalLimits limits = {.min_accel = minimum, .max_accel = maximum};
  return longitudinal_accel_checks(desired_accel, limits);
}

int probe_helper_accel_encoded(int desired_accel, int minimum, int maximum, int inactive) {
  const LongitudinalLimits limits = {.min_accel = minimum, .max_accel = maximum, .inactive_accel = inactive};
  return longitudinal_accel_checks(desired_accel, limits);
}
