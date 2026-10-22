import { reminderCombinedMedication } from "./validate_medication_payload.mjs";

export function monthlyWorkbookRows(payload) {
  const { patients, records, medicationItems, meta } = payload;
  const people = new Map(patients.map(patient => [patient.userid, patient]));
  const reminder = patients.map((patient, index) => [
    index + 1, patient.userid, patient.patientName, patient.gender, patient.age,
    patient.disease, patient.allergyHistory, patient.userType ?? "", patient.sourceTaskId ?? "",
    patient.sourceMonth ?? "", records[index].surgeryName, meta.consumableName,
    reminderCombinedMedication(meta, patient, records[index]), patient.confirmationTime,
    patient.medicationPlan, patient.medicationCycle, "", patient.adverseEvent,
  ]);
  const medication = medicationItems.map((item, index) => {
    const patient = people.get(item.userid);
    return [index + 1, item.userid, patient.patientName, patient.userType ?? "",
      patient.sourceTaskId ?? "", patient.sourceMonth ?? "", item.drugName, item.specification,
      item.singleDose, item.frequency, item.medicationTime, item.treatmentDays, item.precautions];
  });
  return { reminder, medication };
}
