"""Manage class and methods for data freshness indicators."""
import logging
from datetime import datetime
import pandas
from indicator import Indicator
from session import Session

# Load logging configuration
log = logging.getLogger(__name__)


class Freshness(Indicator):
    """Class used to compute indicators of type freshness."""

    def execute(self, authorization: str, session: dict):
        """Execute indicator of type freshness."""

        # Update session status to running
        session_id: int = session['id']
        indicator_id: int = session['indicatorId']
        log.info('Start execution of session Id %i for indicator Id %i.', session_id, indicator_id)
        log.debug('Update session status to Running.')
        Session().update_session_status(authorization, session_id, 'Running')

        # Verify if the list of indicator parameters is valid
        indicator_type_id = session['indicatorByIndicatorId']['indicatorTypeId']
        parameters = session['indicatorByIndicatorId']['parametersByIndicatorId']['nodes']
        parameters = super().verify_indicator_parameters(authorization, indicator_type_id, parameters)

        # Get target data
        dimensions = parameters[4]
        measures = parameters[5]
        target = parameters[8]
        target_request = parameters[9]
        target_data = super().get_data_frame(authorization, target, target_request, dimensions, measures)

        # Evaluate freshness
        alert_operator = parameters[1]  # Alert operator
        alert_threshold = parameters[2]  # Alert threshold
        log.info('Evaluate freshness of target data source.')
        result_data = self.evaluate_freshness(target_data, measures, alert_operator, alert_threshold)

        # Compute session result
        nb_records_alert = Session().compute_session_result(authorization, session_id, alert_operator, alert_threshold, result_data)

        # Send e-mail alert
        if nb_records_alert != 0:
            indicator_name = session['indicatorByIndicatorId']['name']
            distribution_list = parameters[3]  # Distribution list
            super().send_alert(indicator_id, indicator_name, session_id, distribution_list, alert_operator, alert_threshold, nb_records_alert, result_data)

        # Update session status to succeeded
        log.debug('Update session status to Success.')
        Session().update_session_status(authorization, session_id, 'Success')
        log.info('Session Id %i for indicator Id %i completed successfully.', session_id, indicator_id)

    def evaluate_freshness(self, target_data: pandas.DataFrame, measures: str, alert_operator: str, alert_threshold: str):
        """Compute specificities of freshness indicator and return results in a data frame."""

        result_data = target_data
        result_data['current_timestamp'] = datetime.utcnow()

        # Compute delta in minutes and delta description between source and target measures
        for measure in measures:
            source_column = 'current_timestamp'
            target_column = measure
            delta_column = measure + '_delta_minutes'
            delta_description_column = measure + '_delta_description'

            # Enforce measure to datetime data type
            result_data[source_column] = pandas.to_datetime(result_data[source_column], format='%Y-%m-%d %H:%M:%S.%f', errors='ignore')
            result_data[target_column] = pandas.to_datetime(result_data[target_column], format='%Y-%m-%d %H:%M:%S.%f', errors='ignore')

            # Compute delta and delta description
            delta_seconds = (result_data[source_column] - result_data[target_column]).dt.total_seconds()
            result_data[delta_column] = round(delta_seconds/60).astype(int)  # Compute delta in minutes
            result_data[delta_description_column] = pandas.to_timedelta(delta_seconds, unit='s')  # Format delta

        # For each record and measure in data frame test if alert must be sent and update alert column
        result_data['Alert'] = False
        for measure in measures:
            for row_num in result_data.index:
                measure_value = result_data.loc[row_num, measure + '_delta_minutes']
                if self.is_alert(str(measure_value), alert_operator, alert_threshold):
                    result_data.loc[row_num, 'Alert'] = True

        return result_data
