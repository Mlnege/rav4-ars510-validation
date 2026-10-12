#include "probe.c"

// 프로토콜 값과 패킷 길이 경계를 실제 C 함수로 검사한다. 차량 송신은 없다.
int main(void) {
  unsigned long count = 0;
  unsigned long failures = 0;
  uint8_t data[64] = {0};
  for (int allowed = 0; allowed <= 1; allowed++) {
    for (unsigned int value = 0; value <= 65535U; value++) {
      set_safety_hooks(SAFETY_TOYOTA, 73);
      init_tests();
      set_controls_allowed(allowed);
      data[0] = value >> 8;
      data[1] = value & 255U;
      int signed_value = value >= 32768U ? (int)value - 65536 : value;
      bool expected = (allowed && signed_value >= -3500 && signed_value <= 2000) || signed_value == 0;
      bool actual = probe_tx(0x343, 0, 8, data);
      failures += actual != expected || get_controls_allowed() != allowed;
      count++;
    }
  }
  for (uint8_t length = 0; length <= 64; length++) {
    for (uint8_t bus = 0; bus <= 3; bus++) {
      set_safety_hooks(SAFETY_TOYOTA, 73);
      init_tests();
      set_controls_allowed(true);
      for (uint8_t i = 0; i < sizeof(data); i++) data[i] = i + length;
      int tx = probe_tx(0x343, bus, length, data);
      if ((length != 8 || bus != 0) && tx > 0) failures++;
      probe_fwd(0x343, bus, length, data);
      count++;
    }
  }
  printf("{\"cases\":%lu,\"failures\":%lu,\"actual_compiled_c\":true}\n", count, failures);
  return failures ? 1 : 0;
}
