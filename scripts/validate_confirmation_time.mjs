function assert(condition, message) {
  if (!condition) throw new Error(message);
}

export function parseDateTime(value, label = "时间") {
  const text = String(value ?? "").trim();
  const parsed = new Date(text.replace(" ", "T") + "+08:00");
  assert(text && !Number.isNaN(parsed.getTime()), `${label}无效：${value}`);
  return parsed;
}

export function validateReminderConfirmation({ patient, reminderValue, inputFormat }) {
  const confirmationText = String(reminderValue ?? "").trim();
  const confirmation = parseDateTime(confirmationText, `${patient.userid}确认时间`);

  if (inputFormat === "medicationReminder13") {
    const sourceText = String(patient.sourceConfirmationTime ?? "").trim();
    assert(sourceText, `${patient.userid}缺少源用药方案确认时间`);
    parseDateTime(sourceText, `${patient.userid}源用药方案确认时间`);
    assert(confirmationText === sourceText, `${patient.userid}确认时间未复用源用药方案确认时间`);
  } else {
    const activation = parseDateTime(patient.activateTime, `${patient.userid}激活时间`);
    assert(confirmation > activation, `${patient.userid}确认时间未晚于激活时间`);
    assert(
      confirmation.getUTCFullYear() === activation.getUTCFullYear()
        && confirmation.getUTCMonth() === activation.getUTCMonth(),
      `${patient.userid}确认时间跨月`,
    );
  }

  const localHour = Number(confirmationText.slice(11, 13));
  assert(localHour >= 6 && localHour <= 21, `${patient.userid}确认时间超出06:00:00–21:59:59`);
  return confirmation;
}
