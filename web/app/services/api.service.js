(function () {
    'use strict';

    angular
        .module('cm.services')
        .factory('api', ApiService)
        .run(createApi);


    function ApiService($resource, _) {
        var extraMethods = {
            'query': {method: 'GET', isArray: false},
            'update': {method: 'PUT'},
            'patch': {method: 'PATCH'}
        };

        var service = {
            defaultConfig: {id: '@id'},
            extraMethods: extraMethods,
            base_url: '',
            add: add
        };

        return service;

        ///////////////

        function add(config) {
            var params,
                url;
            // If the add() function is called with a
            // String, create the default configuration.
            if (angular.isString(config)) {
                var configObj = {
                    resource: _.camelCase(config),
                    url: service.base_url + '/api/' + config
                };
                //console.log(configObj.url);

                config = configObj;
            }
            // If the url follows the expected pattern, we can set cool defaults
            if (!config.unnatural) {
                var orig = angular.copy(service.defaultConfig);
                params = angular.extend(orig, config.params);
                url = config.url + '/:id';
                // otherwise we have to declare the entire configuration.
            } else {
                params = config.params;
                url = config.url;
            }
            // If we supply a method configuration, use that instead of the default extra.
            var methods = config.methods || service.extraMethods;
            service[config.resource] = $resource(url, params, methods);
            return service;
        }
    }


    function createApi($location, api, $resource) {
        var cm_base_url = '';  // http://' + $location.host() + ':33610';
        api.base_url = cm_base_url;
        api.add({resource: 'cm', url: cm_base_url + '/api'});
        api.add('os');
        api.add({resource: 'cpu', url: cm_base_url + '/api/os/cpu'});
        api.add({resource: 'memory', url: cm_base_url + '/api/os/memory'});
        api.add({resource: 'disk', url: cm_base_url + '/api/os/disk'});
        api.add({resource: 'authenticate', url: cm_base_url + '/api/authenticate', params: {}, unnatural: true});
        api.add('mailings');
        api.add('recipients');
        api.add('satellites');
        api.add('hourly-stats');
        api.add({resource: 'fw', url: '/api/fw'});
        api.add({resource: 'fw_network', url: '/api/fw/network'});
        api.add({resource: 'fw_time', url: '/api/fw/time'});
        api.add({resource: 'fw_all_tz', url: '/api/fw/time/all_tz'});
        api.fw_all_tz = $resource('/api/fw/time/all_tz');

    }


}());
