// Keep the tiny offline lab-reference card synchronized with research outputs.
import { readFileSync, mkdirSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';

const root = resolve(import.meta.dirname, '..');
const joint = JSON.parse(readFileSync(resolve(root, 'docs/data/dynamic_squat_angle_match.json'), 'utf8'));
const emg = JSON.parse(readFileSync(resolve(root, 'docs/data/dynamic_squat_emg_pilot.json'), 'utf8'));
const emgPhase = JSON.parse(readFileSync(resolve(root, 'docs/data/squat_emg_phase_loso.json'), 'utf8'));
const externalEmgPhase = JSON.parse(readFileSync(resolve(root, 'docs/data/same_limb_squat_emg_external.json'), 'utf8'));
const phaseJointMoments = JSON.parse(readFileSync(resolve(root, 'docs/data/squat_phase_joint_moment_loso.json'), 'utf8'));
const manualInputMoments = JSON.parse(readFileSync(resolve(root,
  'docs/data/squat_manual_input_joint_moment_loso.json'), 'utf8'));
const benchmark = JSON.parse(readFileSync(resolve(root, 'docs/data/dynamic_squat_loso_benchmark.json'), 'utf8'));
const templateGrf = JSON.parse(readFileSync(resolve(root, 'docs/data/squat_template_grf_benchmark.json'), 'utf8'));
const deepTemplateGrf = JSON.parse(readFileSync(resolve(root, 'docs/data/squat_template_grf_117_benchmark.json'), 'utf8'));
const tempoSelection = JSON.parse(readFileSync(resolve(root, 'docs/data/squat_tempo_loso_benchmark.json'), 'utf8'));
const twoParameterInputs = JSON.parse(readFileSync(resolve(root, 'docs/data/squat_two_parameter_input_benchmark.json'), 'utf8'));
const copAudit = JSON.parse(readFileSync(resolve(root, 'docs/data/squat_cop_excursion_audit.json'), 'utf8'));
const copRegistration = JSON.parse(readFileSync(resolve(root, 'docs/data/squat_cop_registration.json'), 'utf8'));
const markerCopUnloaded = JSON.parse(readFileSync(resolve(root, 'docs/data/squat_marker_cop_phase_loso.json'), 'utf8'));
const markerCopLoaded = JSON.parse(readFileSync(resolve(root, 'docs/data/squat_marker_cop_phase_loso_25lbs.json'), 'utf8'));
const externalCopTransfer = JSON.parse(readFileSync(resolve(root, 'docs/data/groundlink_squat_cop_transfer.json'), 'utf8'));
const groundlink = JSON.parse(readFileSync(resolve(root, 'docs/data/groundlink_squat_template_benchmark.json'), 'utf8'));
const loadedTemplateGrf = JSON.parse(readFileSync(resolve(root, 'docs/data/loaded_squat_template_grf_benchmark.json'), 'utf8'));
const knownLoadSupport = JSON.parse(readFileSync(resolve(root, 'docs/data/inail_loaded_lift_support_benchmark.json'), 'utf8'));
const bodyMotionProbe = JSON.parse(readFileSync(resolve(root, 'docs/data/inail_body_motion_probe.json'), 'utf8'));
const demoProtocol = JSON.parse(readFileSync(resolve(root, 'src/data/demo_motion_protocol.json'), 'utf8'));
const sensitivity = JSON.parse(readFileSync(resolve(root, 'docs/data/dynamic_squat_force_sensitivity.json'), 'utf8'));
const subjectMuscles = JSON.parse(readFileSync(resolve(root, 'docs/data/subject_muscle_parameter_audit.json'), 'utf8'));
const bilateral = JSON.parse(readFileSync(resolve(root, 'docs/data/full_bilateral_static_optimization_audit.json'), 'utf8'));
const deepCapacity = ['AB01', 'AB02'].map(subject => JSON.parse(readFileSync(resolve(root,
  `docs/data/bilateral_deep_squat_joint_capacity${subject === 'AB01' ? '' : `_${subject}`}.json`), 'utf8')));
const capacityPoseCheck = JSON.parse(readFileSync(resolve(root,
  'docs/data/bilateral_deep_squat_capacity_pose_check.json'), 'utf8'));
const lengthCapacity = JSON.parse(readFileSync(resolve(root,
  'docs/data/bilateral_deep_squat_length_capacity.json'), 'utf8'));
const crossModelCapacity = JSON.parse(readFileSync(resolve(root,
  'docs/data/high_flex_length_capacity.json'), 'utf8'));
const fullBodyLumbar = JSON.parse(readFileSync(resolve(root,
  'docs/data/full_body_lumbar_capacity.json'), 'utf8'));
const kneeRangeValidity = JSON.parse(readFileSync(resolve(root,
  'docs/data/high_flex_knee_range_validity.json'), 'utf8'));
const idNoFreeMoment = ['ab01', 'ab02'].flatMap(subject => ['0lbs', '25lbs'].map(condition =>
  JSON.parse(readFileSync(resolve(root,
    `docs/data/dynamic_squat_id_replay_${subject}_${condition}_no_free_moment.json`), 'utf8'))));
const highFlexFull = JSON.parse(readFileSync(resolve(root,
  'docs/data/high_flex_full_squat_capacity.json'), 'utf8'));
const highFlexEmg = JSON.parse(readFileSync(resolve(root,
  'docs/data/high_flex_squat_emg_prior_pilot.json'), 'utf8'));
const highFlexCandidateId = JSON.parse(readFileSync(resolve(root,
  'docs/data/high_flex_candidate_id_alignment.json'), 'utf8'));
const highFlexCandidateCapacity = JSON.parse(readFileSync(resolve(root,
  'docs/data/high_flex_candidate_id_capacity.json'), 'utf8'));
const highFlexStaticOptimization = JSON.parse(readFileSync(resolve(root,
  'docs/data/high_flex_static_optimization_audit.json'), 'utf8'));
if (Object.keys(joint.subjects).length !== 12 || Object.keys(emg.subjects).length !== 12 || Object.keys(benchmark.subjects).length !== 12) {
  throw new Error('The squat evidence card requires all 12 source participants.');
}
if (emgPhase.status !== 'research_only_no_personal_muscle_force_or_activation_prediction' ||
    emgPhase.loads['0lbs'].participants.length !== 12 ||
    emgPhase.loads['25lbs'].participants.length !== 12 ||
    Object.values(emgPhase.loads).some(load => Object.values(load.repetitions).some(count => count < 1))) {
  throw new Error('The squat EMG phase audit requires complete 12-person records.');
}
if (externalEmgPhase.status !== 'external_no_standardized_load_squat_emg_shape_test_only_no_loaded_force_validation' ||
    externalEmgPhase.summary.participants !== 30 ||
    externalEmgPhase.participantResults.length !== 30 ||
    externalEmgPhase.templateCurve.length !== 99 ||
    externalEmgPhase.externalGroupMedianCurve.length !== 99) {
  throw new Error('The external 30-person RF EMG phase audit is missing or inconsistent.');
}
if (knownLoadSupport.status !== 'external_vertical_support_force_only_not_barbell_or_muscle_force' ||
    knownLoadSupport.summary.eligibleParticipants !== 10 ||
    knownLoadSupport.summary.acceptedTrials !== 84 ||
    knownLoadSupport.summary.participantsBoxAccelerationBeatsStatic !== 10 ||
    !['moreSmoothing', 'primary', 'lessSmoothing'].every(key =>
      knownLoadSupport.accelerationFilterSensitivity[key].participantsBeatingStatic === 10) ||
    knownLoadSupport.trials.length !== 84) {
  throw new Error('The independent known-load support-force audit is missing or inconsistent.');
}
if (bodyMotionProbe.status !== 'exploratory_measured_marker_com_proxy_not_phone_prediction' ||
    bodyMotionProbe.summary.participants !== 10 || bodyMotionProbe.summary.trials !== 84 ||
    bodyMotionProbe.summary.participantsBodyAndBoxBeatsBoxOnly !== 9 ||
    bodyMotionProbe.trials.length !== knownLoadSupport.trials.length) {
  throw new Error('The measured body-motion probe is missing or inconsistent.');
}
const phaseJointUnloaded = phaseJointMoments.loads['0lbs'];
if (manualInputMoments.status !==
    'optimistic_laboratory_manual_input_squat_joint_moment_screen_not_personal_or_muscle_force_validation' ||
    manualInputMoments.loads['0lbs'].subjects !== 12 ||
    manualInputMoments.loads['0lbs'].repetitions !== 39 ||
    manualInputMoments.loads['25lbs'].subjects !== 12 ||
    manualInputMoments.loads['25lbs'].repetitions !== 36 ||
    ['0lbs', '25lbs'].some(load => ['hip_flexion_r_moment', 'knee_angle_r_moment'].some(target => {
      const row = manualInputMoments.loads[load].summary[target];
      return !Number.isFinite(row.phaseMedianSubjectMae) ||
        !Number.isFinite(row.coarse_manual.subjectMedianMaeNmPerKg) ||
        row.coarse_manual.pairedMedianImprovementBootstrap95.length !== 2;
    })) ||
    manualInputMoments.loads['0lbs'].summary.hip_flexion_r_moment.phaseMedianSubjectMae !==
      phaseJointUnloaded.summary.hip_flexion_r_moment.subjectMedianPhaseMaeNmPerKg) {
  throw new Error('The hand-enterable joint-moment input audit is missing or inconsistent.');
}
if (phaseJointMoments.status !== 'research_phase_reference_not_phone_personal_joint_or_muscle_force_validation' ||
    ['hip_flexion_r_moment', 'knee_angle_r_moment'].some(target => {
      const summary = phaseJointUnloaded.summary[target];
      const curve = phaseJointUnloaded.descriptiveGroupShape[target];
      return summary.participants !== 12 || summary.repetitions !== 39 ||
        !Number.isFinite(summary.subjectMedianPhaseMaeNmPerKg) ||
        ['p10', 'median', 'p90'].some(key => curve[key]?.length !== 99) ||
        curve.median.some((value, i) => !Number.isFinite(value) ||
          curve.p10[i] > value || value > curve.p90[i]);
    })) {
  throw new Error('The 12-person phase joint-moment benchmark is missing or inconsistent.');
}
for (const curve of Object.values(emgPhase.loads['0lbs'].descriptiveGroupShape)) {
  if (['p25', 'median', 'p75'].some(key => curve[key]?.length !== 99) ||
      curve.median.some((value, i) => !Number.isFinite(value) ||
        curve.p25[i] > value || value > curve.p75[i])) {
    throw new Error('The squat EMG phase curves must have 99 ordered finite values.');
  }
}
if (templateGrf.status !== 'research_only_not_validated_personal_ground_force_or_muscle_force' ||
    templateGrf.summary.subjects !== 12 || templateGrf.summary.reps < 12 ||
    templateGrf.viewerDefaultDurationS !== demoProtocol.cycleDurationS) {
  throw new Error('The squat evidence card requires the 12-person template GRF audit.');
}
if (deepTemplateGrf.status !== templateGrf.status || deepTemplateGrf.viewerDepthTargetDeg !== 117 ||
    deepTemplateGrf.summary.subjects !== templateGrf.summary.subjects ||
    deepTemplateGrf.summary.reps !== templateGrf.summary.reps ||
    deepTemplateGrf.repetitions.some((item, index) => {
      const original = templateGrf.repetitions[index];
      return item.subject !== original.subject || item.startS !== original.startS || item.endS !== original.endS;
    })) {
  throw new Error('The default and deeper squat GRF audits must compare the same repetitions.');
}
if (tempoSelection.status !== 'internal_leave_one_subject_out_tempo_sensitivity_not_personal_validation' ||
    tempoSelection.summary.subjects !== templateGrf.summary.subjects ||
    tempoSelection.summary.reps !== templateGrf.summary.reps ||
    tempoSelection.summary.heldOutMedianDefault28sMaeRatio !== templateGrf.summary.subjectMedianFixedTemplateMaeRatio) {
  throw new Error('The tempo-selection audit must use the same unloaded repetitions and default benchmark.');
}
if (twoParameterInputs.status !== 'optimistic_measured_input_sensitivity_not_phone_personal_validation' ||
    twoParameterInputs.summary.subjects !== templateGrf.summary.subjects ||
    twoParameterInputs.summary.reps !== templateGrf.summary.reps ||
    twoParameterInputs.summary.subjectMedianMaeBodyWeightRatio.default !== templateGrf.summary.subjectMedianFixedTemplateMaeRatio) {
  throw new Error('The two-parameter input audit must use the same unloaded repetitions and default benchmark.');
}
if (copAudit.status !== 'laboratory_pressure_center_input_audit_not_phone_prediction' ||
    copAudit.summary.subjects !== templateGrf.summary.subjects ||
    copAudit.summary.reps !== templateGrf.summary.reps ||
    copAudit.summary.rejectedReps !== 0) {
  throw new Error('The pressure-center audit must use the same unloaded repetitions.');
}
const registeredFeet = copRegistration.cases.flatMap(item => Object.values(item.feet));
if (copRegistration.status !== 'source_coordinate_registration_audit_not_phone_or_muscle_force_validation' ||
    copRegistration.cases.length !== 4 || registeredFeet.length !== 8 ||
    registeredFeet.some(foot => foot.stanceFrames !== 401 ||
      foot.fractionCopWithinExtendedFootRange < 0.95 ||
      foot.copLateralFromFootAxis.p05ToP95ExcursionCm > 5 ||
      !Number.isFinite(foot.negativePlateMomentVsSourceNetAnkleNm.meanAbsoluteDifference) ||
      !Number.isFinite(foot.fixedCop6cmMeasuredForceVsSourceNetAnkleNm.meanAbsoluteDifference) ||
      !Number.isFinite(foot.fixedCop6cmStaticHalfWeightVsSourceNetAnkleNm.meanAbsoluteDifference) ||
      foot.negativePlateMomentVsSourceNetAnkleNm.correlation < 0.9)) {
  throw new Error('The source COP-to-foot registration audit is missing or implausible.');
}
if ([markerCopUnloaded, markerCopLoaded].some((report, index) =>
    report.status !== 'marker_based_cop_lopo_not_phone_or_muscle_force_validation' ||
    report.load !== ['0lbs', '25lbs'][index] ||
    report.leaveOnePersonOut.subjects !== 12 ||
    report.leaveOnePersonOut.trajectories !== [78, 72][index] ||
    report.leaveOnePersonOut.allPersonPhaseMedianCm.length !== 99 ||
    report.excluded.length !== 0) ||
    externalCopTransfer.status !==
      'external_lab_cop_transfer_not_personal_joint_or_muscle_force_validation' ||
    externalCopTransfer.summary.subjects !== 7 ||
    externalCopTransfer.summary.trajectories !== 126) {
  throw new Error('The source and independent-laboratory pressure-center checks are incomplete.');
}
if (groundlink.status !== 'independent_lab_optimistic_alignment_not_personal_force_or_muscle_validation' ||
    groundlink.summary.subjects !== 7 || groundlink.summary.reps !== 63 ||
    groundlink.topFraction !== 0.9 ||
    groundlink.summary.subjectsFixedBeatsStatic > groundlink.summary.subjects) {
  throw new Error('The independent GroundLink squat audit is missing or inconsistent.');
}
const loadedSummary = loadedTemplateGrf.summary['25lbs'];
const unloadedCrosscheck = loadedTemplateGrf.summary['0lbs'];
if (loadedTemplateGrf.status !== 'research_only_not_validated_personal_force_or_muscle_force' ||
    loadedTemplateGrf.viewerDurationS !== demoProtocol.cycleDurationS ||
    loadedTemplateGrf.viewerHeightAssumptionCm !== 175 ||
    loadedSummary.subjects !== 12 || loadedSummary.reps !== 36 ||
    unloadedCrosscheck.subjects !== templateGrf.summary.subjects ||
    unloadedCrosscheck.reps !== templateGrf.summary.reps ||
    unloadedCrosscheck.subjectMedianFixedMaeRatio !== templateGrf.summary.subjectMedianFixedTemplateMaeRatio ||
    loadedTemplateGrf.repetitions.some(row => !Number.isFinite(row.fixedMaeRatio))) {
  throw new Error('The 25-lb phone-template GRF audit is missing or inconsistent.');
}
if (subjectMuscles.modelCount !== 12 || subjectMuscles.summary.max_isometric_force.exactlyUnchangedMuscles > subjectMuscles.muscleCountEach) {
  throw new Error('The squat evidence card requires a consistent muscle parameter audit.');
}
const hipCapacityGroups = deepCapacity.flatMap(report => ['hip_rotation_r', 'hip_rotation_l'].map(name =>
  report.intervalSummary[name].sourceRawCsvAssumingNmPerKg));
if (bilateral.subject !== 'AB01' || bilateral.frameCount !== 101 ||
    bilateral.optimizerFailedFrameCount + bilateral.successfulFrameCount !== bilateral.frameCount ||
    deepCapacity.some((report, index) => report.subject !== ['AB01', 'AB02'][index]) ||
    hipCapacityGroups.some(group => group.frameCount !== 21 || group.exceededFrameCount !== group.frameCount)) {
  throw new Error('The squat evidence card requires a consistent bilateral force-quality audit.');
}
// The card explains why the hip-rotation alarm cannot be read as missing muscle capacity, so the
// re-derivation that established this must describe the same frame and keep its two signatures.
const capacityReplay = capacityPoseCheck.coordinates.hip_rotation_r;
if (capacityPoseCheck.subject !== deepCapacity[0].subject ||
    capacityPoseCheck.timeS !== deepCapacity[0].timeS ||
    Math.abs(capacityReplay.replayedIdMomentNm - deepCapacity[0].coordinates
      .find(row => row.coordinate === 'hip_rotation_r').targetMomentNm) > 1e-2 ||
    capacityPoseCheck.comparisonsUnderminedByDemandUncertainty.length !== 2 ||
    capacityReplay.directionAsymmetryRatio < 10) {
  throw new Error('The squat evidence card requires a consistent capacity re-derivation.');
}
// The card also reports the length-dependent bound, so it must reproduce the audit it extends.
const lengthKnee = lengthCapacity.subjects.AB01.targetFrame.knee_angle_r;
const lengthLumbar = ['AB01', 'AB02'].map(subject =>
  lengthCapacity.subjects[subject].targetFrame.lumbar_extension.demandToLengthBound);
if (lengthCapacity.subjects.AB01.timeS !== deepCapacity[0].timeS ||
    Math.abs(lengthKnee.maximumBoundNm - deepCapacity[0].coordinates
      .find(row => row.coordinate === 'knee_angle_r').optimisticIndependentCapacityNm) > 1e-2 ||
    lengthCapacity.subjects.AB01.interval.knee_angle_r.framesExceedingLengthBound !== 21 ||
    lengthCapacity.subjects.AB02.interval.knee_angle_r.framesExceedingLengthBound !== 0 ||
    !lengthCapacity.subjects.AB01.modelProvenance.kneeExtensors.vas_int_r) {
  throw new Error('The squat evidence card requires a consistent length-dependent capacity audit.');
}
// The card also reports the research-purpose model re-check, so it must be the audited artifact.
const crossKnee = subject => crossModelCapacity.subjects[subject].targetFrame.knee_angle_r;
const crossDeepest = crossModelCapacity.subjects.AB01.sweep['-140.0'];
const crossHasTrunk = Object.keys(crossDeepest.candidate.muscles)
  .some(name => /^(ercspn|intobl|extobl)/.test(name));
if (crossModelCapacity.subjects.AB01.muscleCount.candidate !== 80 ||
    crossModelCapacity.candidateRepositoryRevision === undefined ||
    !(crossKnee('AB01').candidate.demandToLengthBound > 1) ||
    !(crossKnee('AB02').candidate.demandToLengthBound < 1) ||
    crossHasTrunk ||
    !crossModelCapacity.subjects.AB01.candidatePoseClampedCoordinates.includes('knee_angle_r')) {
  throw new Error('The squat evidence card requires a consistent cross-model capacity audit.');
}
// The card states the lumbar gap does not survive a full-body trunk, so that must be the audit.
const lumbarSubject = fullBodyLumbar.subjects.AB01;
if (fullBodyLumbar.flexionCalibration.flexionIsNegative !== true ||
    fullBodyLumbar.modelProvenance.muscleCount !== 520 ||
    !(lumbarSubject.report.capacities.erectorSpinaeOnlyNm >
      3 * lumbarSubject.reducedModelLengthBoundNm) ||
    !(lumbarSubject.demandToErectorSpinaeOnly < 0.5) ||
    Math.abs(lumbarSubject.sourceLumbarJointAboveHipM -
      fullBodyLumbar.levelCorrespondence.fullBodyLowestLevelAboveHipM) > 0.04 ||
    !(fullBodyLumbar.subjects.AB02.demandToErectorSpinaeOnly < 0.5)) {
  throw new Error('The squat evidence card requires a consistent full-body lumbar audit.');
}
// The card now qualifies the right-knee comparison with the candidate's own data range, so the
// validity audit has to agree: the splines end at 120 deg, nothing inside that range exceeds either
// model's bound, and only AB01 exceeds beyond it.
const kneeValiditySubjects = ['AB01', 'AB02'];
const kneeValiditySummary = subject => kneeRangeValidity.subjects[subject].summary;
const insideMax = (subject, model) => kneeValiditySummary(subject).within[`${model}MaximumRatio`];
const outsideOverOne = (subject, model) =>
  kneeValiditySummary(subject).beyond[`${model}FramesOverOne`];
if (Math.abs(kneeRangeValidity.patellofemoralSplineLimitDeg - 120) > 0.01 ||
    kneeValiditySubjects.some(subject =>
      kneeValiditySummary(subject).within.sourceFramesOverOne !== 0 ||
      kneeValiditySummary(subject).within.candidateFramesOverOne !== 0 ||
      !(insideMax(subject, 'source') < 1) || !(insideMax(subject, 'candidate') < 1)) ||
    outsideOverOne('AB01', 'candidate') === 0 || outsideOverOne('AB02', 'candidate') !== 0 ||
    kneeRangeValidity.subjects.AB01.momentArmProfile.slopeAtBoundaryCmPerDeg.signFlip !== true ||
    Math.abs(kneeRangeValidity.subjects.AB01.momentArmProfile.maximumAbsoluteArm
      .appliedFlexionDeg - kneeRangeValidity.patellofemoralSplineLimitDeg) > 0.01) {
  throw new Error('The squat evidence card requires a consistent knee validity-range audit.');
}
const idErrors = idNoFreeMoment.flatMap(report => Object.values(report.moments)
  .map(moment => moment.mae_if_csv_is_nm_per_kg));
if (idNoFreeMoment.some(report => report.forcePlateFreeMomentIncluded !== false ||
    report.samples !== 401) || idErrors.length !== 12 ||
    idErrors.some(value => !Number.isFinite(value) || value > 3.5)) {
  throw new Error('The squat evidence card requires the four independent ID replay audits.');
}
const highFlexSubjects = ['AB01', 'AB02'];
if (highFlexFull.status !== 'research_only_measured_ik_id_feasibility_not_personal_force' ||
    highFlexEmg.status !== 'research_only_emg_trend_screen_not_personal_muscle_force' ||
    highFlexEmg.strengthMultiplier !== 4.2 ||
    highFlexSubjects.some(subject => {
      const full = highFlexFull.subjects[subject];
      const pilot = highFlexEmg.subjects[subject];
      return !full || !pilot || full.totalSampledFrames !== 101 ||
        full.feasibleAtAnyUniformStrength + full.excludedOutsideKneeRange !== 101 ||
        full.nominalStrengthFeasible > full.feasibleAtAnyUniformStrength ||
        pilot.solvedFrames < 15 || pilot.solverFailures.length !== 0 ||
        Object.keys(pilot.channelTrends).length !== 16;
    })) {
  throw new Error('The measured two-subject muscle-force and EMG gates are missing or inconsistent.');
}
const highFlexEmgSummary = Object.fromEntries(highFlexSubjects.map(subject => {
  const channels = Object.values(highFlexEmg.subjects[subject].channelTrends)
    .filter(row => row.spearman !== null);
  return [subject, {
    comparableChannels: channels.length,
    modelBeatsKneeDepthChannels: channels.filter(row =>
      Math.abs(row.spearman) > Math.abs(row.kneeFlexionBaselineSpearman)).length,
  }];
}));
const candidateDeep = highFlexCandidateId.windows.deep;
const staticRun = (strength) => highFlexStaticOptimization.runs.find(run =>
  run.run === `AB02_23.6_23.7_strength${strength}_physiology`);
const static4p2 = staticRun(4.2);
const static6 = staticRun(6);
if (highFlexCandidateId.status !== 'research_only_source_vs_candidate_inverse_dynamics' ||
    highFlexCandidateCapacity.status !== 'research_only_candidate_id_capacity_not_personal_muscle_force' ||
    highFlexStaticOptimization.status !== 'research_only_high_flex_static_optimization_rejected_for_personal_force' ||
    candidateDeep.frameCount !== 21 || highFlexCandidateCapacity.frames.length !== 21 ||
    !static4p2 || !static6 || static4p2.failedFrameCount !== 13 ||
    static6.failedFrameCount !== 0 ||
    static4p2.convergedFrameCount + static4p2.failedFrameCount !== 21 ||
    static6.convergedFrameCount !== 21 ||
    static6.upperBoundMuscleFrameCountsConverged.bflh_r !== 21 ||
    static6.upperBoundMuscleFrameCountsConverged.bflh_l !== 21 ||
    !Number.isFinite(candidateDeep.tenJointAxes.hip_rotation_r.candidateMinusMappedSourceMedianNm)) {
  throw new Error('Candidate-model ID, capacity, or per-frame optimization audit is inconsistent.');
}
const phase = (id) => {
  const row = joint.cross_subject_summary[id];
  return {
    participants: row.accepted_subjects.length,
    verticalGrfDifferenceMedianN: row.vertical_grf_difference_N.median_of_subject_medians,
    hipExtensionDirectionCount: row.r_hip_moment_loaded_minus_unloaded.subjects_negative,
    rightKneeIncreaseCount: row.r_knee_moment_loaded_minus_unloaded.subjects_positive,
  };
};
const channel = (name) => {
  const row = emg.cross_subject_summary.ascent.channel_ratios[name];
  return { participants: row.eligible_subjects.length, ratioMedian: row.median,
    increaseCount: row.subjects_above_one };
};
const output = {
  schemaVersion: 26,
  status: 'external_lab_reference_not_personal_prediction',
  addedLoadLb: 25,
  studyParticipants: 12,
  descent: phase('descent'),
  ascent: phase('ascent'),
  ascentEmg: { rightGluteMax: channel('RGMAX'), rightBicepsFemoris: channel('RBF'),
    rightVastusLateralis: channel('RVL') },
  phaseEmgValidation: {
    subjects: emgPhase.loads['0lbs'].participants.length,
    unloadedReps: Object.values(emgPhase.loads['0lbs'].repetitions).reduce((a, b) => a + b, 0),
    loadedReps: Object.values(emgPhase.loads['25lbs'].repetitions).reduce((a, b) => a + b, 0),
    unloadedRightRectusFemoris: emgPhase.loads['0lbs'].summary.RRF,
    unloadedRightBicepsFemoris: emgPhase.loads['0lbs'].summary.RBF,
    loadedRightVastusLateralis: emgPhase.loads['25lbs'].summary.RVL,
  },
  phaseEmgStudyCurves: emgPhase.loads['0lbs'].descriptiveGroupShape,
  externalPhaseEmgValidation: {
    participants: externalEmgPhase.summary.participants,
    templateBeatsStatic: externalEmgPhase.summary.templateBeatsStatic,
    medianPairedImprovement: externalEmgPhase.summary.medianPairedImprovement,
    oneSidedSignTestP: externalEmgPhase.summary.oneSidedSignTestP,
  },
  externalPhaseEmgSourceUrl: 'https://huggingface.co/datasets/Tdongxu/A_Synchronized_Lower_Limb_AMG_sEMG_and_Mocap',
  knownLoadSupportStudy: {
    participants: knownLoadSupport.summary.eligibleParticipants,
    trials: knownLoadSupport.summary.acceptedTrials,
    staticMaeRatio: knownLoadSupport.summary.participantMedianStaticMaeRatio,
    measuredAccelerationMaeRatio: knownLoadSupport.summary.participantMedianBoxAccelerationMaeRatio,
    participantsImproved: knownLoadSupport.summary.participantsBoxAccelerationBeatsStatic,
    smoothingMaeRange: [
      knownLoadSupport.accelerationFilterSensitivity.moreSmoothing.participantMedianMaeRatio,
      knownLoadSupport.accelerationFilterSensitivity.lessSmoothing.participantMedianMaeRatio,
    ],
  },
  knownLoadSupportSourceUrl: knownLoadSupport.sourceUrl,
  measuredBodyMotionProbe: {
    participants: bodyMotionProbe.summary.participants,
    trials: bodyMotionProbe.summary.trials,
    boxOnlyMaeRatio: bodyMotionProbe.summary.participantMedianBoxOnlyMaeRatio,
    bodyAndBoxMaeRatio: bodyMotionProbe.summary.participantMedianBodyAndBoxMaeRatio,
    improvedParticipants: bodyMotionProbe.summary.participantsBodyAndBoxBeatsBoxOnly,
    pelvisOnlyMaeRatio: bodyMotionProbe.bodyProxyControls.pelvisOnly.participantMedianMaeRatio,
    pelvisOnlyImprovedParticipants: bodyMotionProbe.bodyProxyControls.pelvisOnly.participantsBeatingBoxOnly,
  },
  phaseJointMomentValidation: {
    rightHip: phaseJointUnloaded.summary.hip_flexion_r_moment,
    rightKnee: phaseJointUnloaded.summary.knee_angle_r_moment,
  },
  manualInputJointMomentValidation: Object.fromEntries(['0lbs', '25lbs'].map(load => [load, {
    subjects: manualInputMoments.loads[load].subjects,
    repetitions: manualInputMoments.loads[load].repetitions,
    rightHip: manualInputMoments.loads[load].summary.hip_flexion_r_moment,
    rightKnee: manualInputMoments.loads[load].summary.knee_angle_r_moment,
  }])),
  phaseJointMomentStudyCurves: {
    rightHip: phaseJointUnloaded.descriptiveGroupShape.hip_flexion_r_moment,
    rightKnee: phaseJointUnloaded.descriptiveGroupShape.knee_angle_r_moment,
  },
  heldOutPrediction: {
    participants: benchmark.summary.hip_flexion_r_moment.subject_count,
    hipR2: benchmark.summary.hip_flexion_r_moment.simple.pooled_r2,
    kneeR2: benchmark.summary.knee_angle_r_moment.simple.pooled_r2,
    ascentKneeLoadDirectionCorrect: benchmark.matched_load_change_summary.ascent.knee_angle_r_moment.simple.direction_correct,
    ascentKneeLoadParticipants: benchmark.matched_load_change_summary.ascent.knee_angle_r_moment.subjects.length,
  },
  templateGrf: {
    subjects: templateGrf.summary.subjects,
    reps: templateGrf.summary.reps,
    defaultDurationS: templateGrf.viewerDefaultDurationS,
    staticMaeRatio: templateGrf.summary.subjectMedianStaticMaeRatio,
    fixedTemplateMaeRatio: templateGrf.summary.subjectMedianFixedTemplateMaeRatio,
    deepTemplateMaeRatio: deepTemplateGrf.summary.subjectMedianFixedTemplateMaeRatio,
    subjectsTemplateBeatsStatic: templateGrf.summary.subjectsFixedTemplateBeatsStatic,
    viewerMaxKneeFlexionDeg: templateGrf.viewerKneeFlexionRangeDeg[1],
    observedMedianPeakKneeFlexionDeg: templateGrf.summary.subjectMedianPeakKneeFlexionDeg,
  },
  tempoSelection: {
    heldOutMedianSelectedMaeRatio: tempoSelection.summary.heldOutMedianSelectedMaeRatio,
    heldOutMedianDefault28sMaeRatio: tempoSelection.summary.heldOutMedianDefault28sMaeRatio,
    selectedBeatsDefaultSubjects: tempoSelection.summary.selectedBeatsDefaultSubjects,
    subjects: tempoSelection.summary.subjects,
  },
  twoParameterInputs: {
    subjects: twoParameterInputs.summary.subjects,
    bothMeasuredPresetsMaeRatio: twoParameterInputs.summary.subjectMedianMaeBodyWeightRatio.bothMeasuredPresets,
    bothMeasuredPresetsBeatsDefault: twoParameterInputs.summary.subjectsBeatingDefault.bothMeasuredPresets,
    pairedMedianImprovementRatio: twoParameterInputs.summary.pairedSubjectMedianImprovementVsDefault.bothMeasuredPresets,
  },
  pressureCenterAudit: {
    subjects: copAudit.summary.subjects,
    medianPlateZExcursionCm: copAudit.summary.subjectMedianPlateZExcursionCm,
    medianAbsStartToBottomShiftCm: copAudit.summary.subjectMedianAbsStartToBottomShiftCm,
    registeredParticipants: 2,
    registeredClips: copRegistration.cases.length,
    registeredFootTracks: registeredFeet.length,
    minimumFootForwardExcursionCm: Math.min(...registeredFeet.map(foot => foot.copForwardFromAnkle.p05ToP95ExcursionCm)),
    maximumFootForwardExcursionCm: Math.max(...registeredFeet.map(foot => foot.copForwardFromAnkle.p05ToP95ExcursionCm)),
    maximumPlateToSourceAnkleMaeNm: Math.max(...registeredFeet.map(foot =>
      foot.negativePlateMomentVsSourceNetAnkleNm.meanAbsoluteDifference)),
    minimumFixedCopMeasuredForceMaeNm: Math.min(...registeredFeet.map(foot =>
      foot.fixedCop6cmMeasuredForceVsSourceNetAnkleNm.meanAbsoluteDifference)),
    maximumFixedCopMeasuredForceMaeNm: Math.max(...registeredFeet.map(foot =>
      foot.fixedCop6cmMeasuredForceVsSourceNetAnkleNm.meanAbsoluteDifference)),
    minimumFixedCopStaticWeightMaeNm: Math.min(...registeredFeet.map(foot =>
      foot.fixedCop6cmStaticHalfWeightVsSourceNetAnkleNm.meanAbsoluteDifference)),
    maximumFixedCopStaticWeightMaeNm: Math.max(...registeredFeet.map(foot =>
      foot.fixedCop6cmStaticHalfWeightVsSourceNetAnkleNm.meanAbsoluteDifference)),
  },
  pressureCenterPhaseTransfer: {
    sourceUnloadedSubjects: markerCopUnloaded.leaveOnePersonOut.subjects,
    sourceUnloadedReps: markerCopUnloaded.leaveOnePersonOut.trajectories / 2,
    sourceUnloadedFlatMaeCm: markerCopUnloaded.leaveOnePersonOut.medianSubjectMaeCm.flatTrainMedianCm,
    sourceUnloadedPhaseMaeCm: markerCopUnloaded.leaveOnePersonOut.medianSubjectMaeCm.phaseTrainMedianCm,
    sourceLoadedFlatMaeCm: markerCopLoaded.leaveOnePersonOut.medianSubjectMaeCm.flatTrainMedianCm,
    sourceLoadedPhaseMaeCm: markerCopLoaded.leaveOnePersonOut.medianSubjectMaeCm.phaseTrainMedianCm,
    externalSubjects: externalCopTransfer.summary.subjects,
    externalReps: externalCopTransfer.summary.trajectories / 2,
    externalFlatMaeCm: externalCopTransfer.summary.sourceFlatMedianSubjectMaeCm,
    externalPhaseMaeCm: externalCopTransfer.summary.sourcePhaseMedianSubjectMaeCm,
    externalPhaseBetterSubjects: externalCopTransfer.summary.phaseBetterSubjects,
    externalFlatCopOnlyMomentMaeNm: externalCopTransfer.summary.flatCopOnlyExternalMomentMedianSubjectMaeNm,
    externalPhaseCopOnlyMomentMaeNm: externalCopTransfer.summary.phaseCopOnlyExternalMomentMedianSubjectMaeNm,
  },
  independentSquatGrf: {
    subjects: groundlink.summary.subjects,
    reps: groundlink.summary.reps,
    staticMaeRatio: groundlink.summary.subjectMedianStaticMaeRatio,
    fixedTemplateMaeRatio: groundlink.summary.subjectMedianFixedTemplateMaeRatio,
    fixedBeatsStaticSubjects: groundlink.summary.subjectsFixedBeatsStatic,
    measuredDurationMaeRatio: groundlink.summary.subjectMedianMeasuredDurationTemplateMaeRatio,
  },
  loadedSquatGrf: {
    subjects: loadedSummary.subjects,
    reps: loadedSummary.reps,
    staticMaeRatio: loadedSummary.subjectMedianStaticMaeRatio,
    fixedTemplateMaeRatio: loadedSummary.subjectMedianFixedMaeRatio,
    bodyMotionPlusStaticLoadMaeRatio: loadedSummary.subjectMedianBodyMotionPlusStaticLoadMaeRatio,
    fixedBeatsStaticSubjects: loadedSummary.subjectsFixedBeatsStatic,
    barMotionBeatsStaticLoadSubjects: loadedSummary.subjectsBarMotionBeatsStaticLoad,
  },
  muscleForceSensitivity: {
    subjects: new Set([
      ...sensitivity.summary.ascent.glut_max.eligible_subjects,
      ...sensitivity.summary.ascent.biceps_femoris.eligible_subjects,
    ]).size,
    gluteMaxLoadedForceSpreadMedian: sensitivity.summary.ascent.glut_max.median_torque_fit_loaded_force_max_to_min,
    bicepsFemorisLoadedForceSpreadMedian: sensitivity.summary.ascent.biceps_femoris.median_torque_fit_loaded_force_max_to_min,
  },
  subjectMuscleParameters: {
    models: subjectMuscles.modelCount,
    musclesPerModel: subjectMuscles.muscleCountEach,
    unchangedMaxForceMuscles: subjectMuscles.summary.max_isometric_force.exactlyUnchangedMuscles,
  },
  bilateralForceGate: {
    subject: bilateral.subject,
    testedFrames: bilateral.frameCount,
    optimizerFailedFrames: bilateral.optimizerFailedFrameCount,
    capacitySubjects: deepCapacity.length,
    sourceCsvHipRotationGroupsExceeding: hipCapacityGroups.length,
    framesPerCapacityGroup: hipCapacityGroups[0].frameCount,
    lowestMedianSourceCsvDemandToCapacity: Math.min(...hipCapacityGroups.map(group => group.medianDemandToCapacity)),
    hipRotationBoundDirectionAsymmetryRatio: capacityReplay.directionAsymmetryRatio,
    hipRotationOppositeDirectionCapacityNm: capacityReplay.oppositeDirectionCapacityNm,
    hipRotationCapacityNm: capacityReplay.optimisticCapacityNm,
    hipRotationMusclesWithNegligibleArm: capacityPoseCheck.hipRotationBoundDecomposition
      .hipSpanningMusclesWithArmBelow1mm,
    hipRotationMuscleCount: capacityPoseCheck.muscleCount,
    hipRotationDemandDisagreementToCapacity: capacityReplay.disagreementToCapacity,
    kneeLengthDependentBoundNm: lengthKnee.lengthBoundNm,
    kneeMaximumBoundNm: lengthKnee.maximumBoundNm,
    kneeDemandToLengthBound: lengthKnee.sourceCsvDemandToLengthBound,
    otherSubjectKneeDemandToLengthBound: lengthCapacity.subjects.AB02
      .targetFrame.knee_angle_r.sourceCsvDemandToLengthBound,
    lumbarDemandToLengthBound: Math.max(...lengthLumbar),
    hamstringShareOfKneeBoundNm: Math.round(lengthKnee.muscles
      .filter(row => row.muscle.startsWith('bifem'))
      .reduce((sum, row) => sum + row.maximumCapacityNm, 0)),
    crossModelKneeDemandToLengthBound: crossKnee('AB01').candidate.demandToLengthBound,
    crossModelOtherSubjectKneeDemandToLengthBound: crossKnee('AB02').candidate.demandToLengthBound,
    crossModelKneeExtensorRatio: Math.round(10 *
      crossDeepest.candidate.extensorsOnlyLengthNm /
      crossDeepest.source.extensorsOnlyLengthNm) / 10,
    crossModelKneeFlexorArtifactNm: crossDeepest.candidate.flexorsActingAsExtensorsMaximumNm,
    crossModelPoseClampedDeg: crossKnee('AB01').candidate.appliedPoseDeg,
    crossModelHasTrunkMuscles: crossHasTrunk,
    lumbarFullBodyMuscleCount: fullBodyLumbar.modelProvenance.muscleCount,
    lumbarFullBodyErectorCapacityNm: Math.round(
      lumbarSubject.report.capacities.erectorSpinaeOnlyNm),
    lumbarFullBodyDemandToCapacity: lumbarSubject.demandToErectorSpinaeOnly,
    lumbarFullBodyOtherSubjectDemandToCapacity:
      fullBodyLumbar.subjects.AB02.demandToErectorSpinaeOnly,
    lumbarFullBodyErectorRatio: Math.round(10 *
      lumbarSubject.report.capacities.erectorSpinaeOnlyNm /
      lumbarSubject.reducedModelLengthBoundNm) / 10,
    kneeValidRangeSplineLimitDeg: Math.round(kneeRangeValidity.patellofemoralSplineLimitDeg),
    kneeValidRangeInsideWorstSourceRatio: Math.max(
      ...kneeValiditySubjects.map(subject => insideMax(subject, 'source'))),
    kneeValidRangeInsideWorstCandidateRatio: Math.max(
      ...kneeValiditySubjects.map(subject => insideMax(subject, 'candidate'))),
    kneeValidRangeInsideFramesOverOne: kneeValiditySubjects.reduce((total, subject) =>
      total + kneeValiditySummary(subject).within.sourceFramesOverOne +
      kneeValiditySummary(subject).within.candidateFramesOverOne, 0),
    kneeValidRangeOutsideFrames: kneeValiditySummary('AB01').beyond.frames,
    kneeValidRangeOutsideCandidateFramesOverOne: outsideOverOne('AB01', 'candidate'),
  },
  highFlexForceGate: Object.fromEntries(highFlexSubjects.map(subject => [subject, {
    withinKneeRangeFrames: highFlexFull.subjects[subject].feasibleAtAnyUniformStrength,
    nominalStrengthFeasibleFrames: highFlexFull.subjects[subject].nominalStrengthFeasible,
    peakRequiredNominalStrengthMultiplier: highFlexFull.subjects[subject].nominalMultiplier.maximum,
  }])),
  highFlexEmgGate: {
    strengthMultiplier: highFlexEmg.strengthMultiplier,
    subjects: highFlexEmgSummary,
  },
  highFlexCandidateGate: {
    subject: highFlexCandidateCapacity.subject,
    frames: candidateDeep.frameCount,
    rightHipRotationCandidateMinusMappedSourceMedianNm:
      candidateDeep.tenJointAxes.hip_rotation_r.candidateMinusMappedSourceMedianNm,
    ownIdNominalStrengthMultiplierMedian: highFlexCandidateCapacity.nominal.median,
    ownIdPassiveAdjustedMultiplierMedian: highFlexCandidateCapacity.passiveAdjusted.median,
    staticOptimization4p2FailedFrames: static4p2.failedFrameCount,
    staticOptimization6xFailedFrames: static6.failedFrameCount,
    staticOptimization6xSaturatedBicepsFemorisLongHeadFrames:
      static6.upperBoundMuscleFrameCountsConverged.bflh_r,
  },
  independentIdReplay: {
    participants: 2,
    conditions: 4,
    rightHipKneeAnkleComparisons: idErrors.length,
    maximumMeanAbsoluteErrorNm: Math.max(...idErrors),
    forcePlateFreeMomentsIncluded: false,
  },
  sourceUrl: 'https://www.nature.com/articles/s41597-023-02840-6',
  independentSquatSourceUrl: 'https://csr.bu.edu/groundlink/',
  licenseUrl: 'https://creativecommons.org/licenses/by/4.0/',
};
const target = resolve(root, 'src/data/squat_evidence.json');
mkdirSync(dirname(target), { recursive: true });
writeFileSync(target, `${JSON.stringify(output, null, 2)}\n`);
console.log(`Wrote ${target}`);
