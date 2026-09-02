import assert from "node:assert/strict";

import {
  parseDateTime,
  validateReminderConfirmation,
} from "../scripts/validate_confirmation_time.mjs";

const reminderPatient = {
  userid: "u1",
  activateTime: "",
  sourceConfirmationTime: "2026-08-26 16:16:07",
};

assert.doesNotThrow(() => validateReminderConfirmation({
  patient: reminderPatient,
  reminderValue: "2026-08-26 16:16:07",
  inputFormat: "medicationReminder13",
}));

assert.throws(() => validateReminderConfirmation({
  patient: reminderPatient,
  reminderValue: "2026-08-26 16:16:08",
  inputFormat: "medicationReminder13",
}), /未复用源用药方案确认时间/);

assert.doesNotThrow(() => validateReminderConfirmation({
  patient: { userid: "u2", activateTime: "2026-08-26 15:16:07" },
  reminderValue: "2026-08-26 15:46:07",
  inputFormat: "monthlyPatient18",
}));

assert.throws(() => validateReminderConfirmation({
  patient: { userid: "u3", activateTime: "" },
  reminderValue: "2026-08-26 15:46:07",
  inputFormat: "monthlyPatient18",
}), /激活时间无效/);

assert.throws(() => parseDateTime("", "测试时间"), /测试时间无效/);
console.log("validate_confirmation_time tests passed");
