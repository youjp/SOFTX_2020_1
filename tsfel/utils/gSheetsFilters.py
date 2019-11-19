import ast
import json

import gspread
import numpy as np
from oauth2client.service_account import ServiceAccountCredentials
from tsfel.utils.calculate_complexity import compute_complexity

import tsfel


def filter_features(features, filters):
    """Filtering features based on Google sheet.

    Parameters
    ----------
    features : dict
        Dictionary with features
    filters : dict
        Filters from Google sheets

    Returns
    -------
    dict
        Filtered features

    """
    features_all = list(np.concatenate([list(features[dk].keys()) for dk in sorted(features.keys())]))
    list_shown, feat_shown = list(features.keys()), features_all
    cost_shown = features_all
    if filters['2'] != {}:
        list_hidden = filters['2']['hiddenValues']
        list_shown = [dk for dk in features.keys() if dk not in list_hidden]
    if filters['1'] != {}:
        feat_hidden = filters['1']['hiddenValues']
        feat_shown = [ff for ff in features_all if ff not in feat_hidden]
    if filters['3'] != {}:
        cost_numbers = filters['3']['hiddenValues']
        cost_hidden = list(np.concatenate([['Constant', 'Log'] if int(cn) == 1 else
                                           ['Squared', 'Nlog'] if int(cn) == 3 else ['Linear']
                                           if int(cn) == 2 else ['Unknown'] for cn in cost_numbers]))
        cost_shown = []
        for dk in features.keys():
            cost_shown += [ff for ff in features[dk].keys() if features[dk][ff]['Complexity'] not in cost_hidden]
    features_filtered = list(np.concatenate([list(features[dk].keys())
                                             for dk in sorted(features.keys()) if dk in list_shown]))
    features_filtered = [ff for ff in features_filtered if ff in feat_shown]
    features_filtered = [cc for cc in features_filtered if cc in cost_shown]

    return features_filtered


def extract_sheet(gsheet_name):
    """Interaction between features.json and Google sheets.

    Parameters
    ----------
    gsheet_name : str
        Google Sheet name

    Returns
    -------
    dict
        Features

    """
    # Path to Tsfel
    lib_path = tsfel.__path__

    # Access features.json
    path_json = lib_path[0] + '/feature_extraction/features.json'

    # Read features.json into a dictionary of features and parameters
    dict_features = json.load(open(path_json))

    len_stat = len(dict_features['Statistical'].keys())
    len_temp = len(dict_features['Temporal'].keys())
    len_spec = len(dict_features['Spectral'].keys())

    # Access Google sheet
    # Scope and credentials using the content of client_secret.json file
    scope = ['https://spreadsheets.google.com/feeds',
             'https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_name(lib_path[0] + '/utils/client_secret.json', scope)

    # Create a gspread client authorizing it using those credentials
    client = gspread.authorize(creds)

    # and pass it to the spreadsheet name, getting access to sheet1
    confManager = client.open(gsheet_name)
    sheet = confManager.sheet1
    metadata = confManager.fetch_sheet_metadata()

    # Features from Google sheet
    list_of_features = sheet.col_values(2)[4:]
    list_domain = sheet.col_values(3)[4:]

    try:
        filters = metadata['sheets'][sheet.id]['basicFilter']['criteria']
        list_filt_features = filter_features(dict_features, filters)
    except KeyError:
        print('No filters running. Check Google Sheet filters.')
        list_filt_features = list_of_features.copy()

    use_or_not = ['TRUE' if lf in list_filt_features else 'FALSE' for lf in list_of_features]

    assert len(list_of_features) <= (len_spec + len_stat + len_temp), \
        "To insert a new feature, please add it to data/features.json with the code in src/utils/features.py"

    # adds a new feature in Google sheet if it is missing from features.json
    if len(list_of_features) < (len_spec + len_stat + len_temp):

        # new feature was added
        for domain in dict_features.keys():
            for feat in dict_features[domain].keys():
                if feat not in list_of_features:
                    feat_dict = dict_features[domain][feat]
                    param = ''
                    fs = 'no'

                    # Read parameters from features.json
                    if feat_dict['parameters']:
                        param = feat_dict['parameters'].copy()
                        if 'fs' in feat_dict['parameters']:
                            fs = 'yes'
                            param.pop('fs')
                            if len(param) == 0:
                                param = ''

                    curve = feat_dict['Complexity']
                    curves_all = ['Linear', 'Log', 'Square', 'Nlog', 'Constant']
                    complexity = compute_complexity(feat, domain,
                                                    path_json) if curve not in curves_all else 1 if curve in [
                        'Constant', 'Log'] else 2 if curve == 'Linear' else 3
                    new_feat = ['', feat, domain, complexity, fs, str(param),
                                feat_dict['description']]

                    # checks if the Google sheet has no features
                    if sheet.findall(domain) == []:
                        idx_row = 4
                    else:
                        idx_row = sheet.findall(domain)[-1].row

                    # Add new feature at the end of feature domain
                    sheet.insert_row(new_feat, idx_row + 1)
                    print(feat + " feature was added to Google Sheet.")

        # Update list of features and domains from Google sheet
        list_of_features = sheet.col_values(2)[4:]
        list_domain = sheet.col_values(3)[4:]

        # Update filtered features from Google sheet
        try:
            filters = metadata['sheets'][sheet.id]['basicFilter']['criteria']
            list_filt_features = filter_features(dict_features, filters)
        except KeyError:
            list_filt_features = list_of_features.copy()
            print('')

        use_or_not = ['TRUE' if lf in list_filt_features else 'FALSE' for lf in list_of_features]

    assert 'TRUE' in use_or_not, 'Please select a feature to extract!' + '\n'

    # Update dict of features with changes from Google sheet
    for ii, feature in enumerate(list_of_features):
        domain = list_domain[ii]
        if use_or_not[ii] == 'TRUE':
            dict_features[domain][feature]['use'] = 'yes'

            # Check features parameters from Google sheet
            if sheet.cell(ii + 5, 6).value != '':
                param_sheet = ast.literal_eval(sheet.cell(ii + 5, 6).value)

                # update dic of features based on Google sheet
                dict_features[domain][feature]['parameters'] = param_sheet

            # Check features that use sampling frequency parameter
            if sheet.cell(ii + 5, 5).value != 'no':

                # update dict of features based on Google sheet fs
                param_fs_sheet = int(sheet.cell(4, 9).value)
                dict_features[domain][feature]['parameters']['fs'] = param_fs_sheet
        else:
            dict_features[domain][feature]['use'] = 'no'

    return dict_features
