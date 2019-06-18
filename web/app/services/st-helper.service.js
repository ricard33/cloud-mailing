/**
 * Created by ricard on 08/11/2015.
 */

(function () {
    "use strict";

    angular.module('cm.st-helper', [])
        .factory('stHelper', stHelper);

    function stHelper() {
        return {
            addOrderingPrefix: function (tableState) {
                var ordering = "";

                if (tableState.sort.predicate !== undefined) {
                    ordering = tableState.sort.reverse ? "-" : "";
                    ordering += tableState.sort.predicate;
                }

                return ordering;
            },
            getSearch: function (tableState) {
                var searchTerms = "";
                if (tableState.search.predicateObject !== undefined) {
                    searchTerms = tableState.search.predicateObject;
                }

                return searchTerms;
            }
        };
    }

}());
